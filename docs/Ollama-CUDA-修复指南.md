# Ollama CUDA 崩溃诊断与修复指南

> 诊断时间：2026-09-13 · 诊断对象：本机 Ollama 0.34.0 · 结论：**用 `OLLAMA_FLASH_ATTENTION=0` 修复**
> 本文所有结论均为本机实测，不是推测。

## 一、症状

任何**对话模型**（llama 系）只要走 CUDA 后端，就在 llama-server 的 warmup 阶段崩溃：

```
CUDA error: shared object initialization failed
ggml/src/ggml-cuda/ggml-cuda.cu:108: CUDA error
  current device: 0, in function ggml_cuda_flash_attn_ext_mma_f16_case at fattn-mma-f16.cuh:1973
  cudaFuncSetAttribute(..., cudaFuncAttributeMaxDynamicSharedMemorySize, nbytes_shared_total)
llama-server terminated: exit status 0xc0000409
```

对外的 HTTP 表现是 `500 {"error":"llama-server process has terminated: exit status 0xc0000409..."}`。

**关键误导点**：报错里既有「内存」字样又有 Windows 的「栈缓冲区溢出」，而且崩溃前日志明确写着
`common_fit_params: successfully fit params to free device memory`、模型层也成功卸载到 GPU —— 看起来
像显存不足，实际不是。

## 二、本机环境

| 项 | 值 |
|---|---|
| Ollama | 0.34.0（`%LOCALAPPDATA%\Programs\Ollama`） |
| GPU | NVIDIA GeForce RTX 4060 Laptop（Ada，sm_89），**8GB 显存** |
| 驱动 | 595.97 / CUDA UMD 13.2 |
| CPU / 内存 | AMD Ryzen 9 7945HX（16C/32T）/ 15.7GB |
| 后端库 | 自带 `cuda_v12` 与 `cuda_v13`（本次走 cuda_v13） |
| 模型 | qwen2.5:14b（Q4_K_M，8.37GB）、nomic-embed-text |

## 三、根因

`cudaFuncSetAttribute(cudaFuncAttributeMaxDynamicSharedMemorySize, …)` 在
**Flash Attention MMA 内核**上设置「每块动态共享内存」时失败。

这个上限是**架构硬限制**，与显存余量无关。失败后 CUDA 走 fast-fail，把整个 llama-server
进程带走（`0xc0000409` 是 Windows 对 fast-fail 的通用文案，不是真的栈溢出）。

上游同签名 issue（结论一致）：
- [ollama#18276 · auto-enabled flash attention crashes llama-server at warmup](https://github.com/ollama/ollama/issues/18276) —— 给出已验证解法 `OLLAMA_FLASH_ATTENTION=0`
- [ollama#18232 · num_ctx affects Flash Attention MMA kernel shared memory allocation](https://github.com/ollama/ollama/issues/18232) —— 指出 `num_ctx` 参与该共享内存计算

## 四、修复（推荐做法）

**让 ollama 服务进程带 `OLLAMA_FLASH_ATTENTION=0` 启动**，ollama 就会给 llama-server 传
`--flash-attn off`，绕开 MMA 内核：

```powershell
# 1) 永久写入用户环境变量(对托盘启动的 Ollama 生效)
[Environment]::SetEnvironmentVariable('OLLAMA_FLASH_ATTENTION','0','User')

# 2) 完全退出 Ollama(托盘图标右键退出), 再启动它
#    环境变量只在"服务进程启动时"读取一次, 不重启不生效

# 3) 验证: 日志里应出现 --flash-attn off(而不是 auto)
Select-String "flash-attn" "$env:LOCALAPPDATA\Ollama\server.log" | Select-Object -Last 2

# 4) 跑一个对话模型验证
ollama run qwen2.5:7b "说一句中文"
```

不想改全局环境变量时，可另起一个专用实例（本项目 `config.yaml` 就是这么建议的）：

```powershell
$env:OLLAMA_HOST='127.0.0.1:11438'; $env:OLLAMA_FLASH_ATTENTION='0'
ollama serve
# 然后把 config.yaml 的 llm.providers.local.base_url 指到 127.0.0.1:11438
```

### 代价（必须知道）

- Flash Attention 关闭 → 注意力计算变慢（对 8GB 卡尤其明显）。
- `OLLAMA_KV_CACHE_TYPE` 的 KV 量化依赖 FA，会一并失效 → 长上下文的 KV 缓存更大。
- 好处是**能跑**：上游同款环境实测 42.8 tok/s（RTX 5070 Ti Laptop）。

## 五、已排除的方案（都实测过，别再试）

| 尝试 | 结果 |
|---|---|
| `GGML_CUDA_PDL=0`（关掉 PDL 内核） | ❌ 仍崩在同一行 `ggml-cuda.cu:108`，且 `--flash-attn` 仍是 `auto` |
| 强制 CPU（`OLLAMA_LLM_LIBRARY=cpu` + `CUDA_VISIBLE_DEVICES=-1`） | ⚠️ 不崩，但 14b 需 ~8.5GB 内存且 ollama 禁用 mmap → 本机只剩 4GB 可用，实测不可用 |
| Vulkan 后端（`CUDA_VISIBLE_DEVICES=-1` + `OLLAMA_VULKAN=true`） | ✅ 能跑不崩，但慢：prefill 10.7 t/s、decode 3.0 t/s |
| `OLLAMA_FLASH_ATTENTION=false` 设在客户端进程 | ❌ 无效 —— 该变量必须到达 **serve 进程** |
| `CUDA_VISIBLE_DEVICES=""` | ❌ 与崩溃无关（上游 issue 也验证过） |

## 六、显存/内存的现实约束（选模型时看这个）

RTX 4060 Laptop 可用显存约 **7.1GB**：

| 模型 | 体积 | 卸载情况 | 结果 |
|---|---|---|---|
| qwen2.5:14b Q4_K_M | 8.37GB | 必须部分卸载（31/49 层上 GPU），**额外要 3.58GB 主机 pinned 内存** | 主机内存紧张时 `CUDA_Host buffer` 分配失败 |
| qwen2.5:7b Q4_K_M | ~4.7GB | 可 100% 进显存 | 推荐；不依赖主机内存 |

> 结论：**8GB 卡上跑 14b 要同时满足「FA 关闭 + 3.6GB 空闲主机内存」**；想稳就跑 7b，
> 或者清理浏览器等内存大户后再上 14b。

## 七、顺带确认的事

- **embedding 不受影响**：`nomic-embed-text` 在本机 CUDA 下 **正常**（实测 HTTP 200）→
  AstrBot 的知识库向量化没坏。
- **只有对话模型崩**：因为它们的 warmup 会实例化 FA MMA 内核，embedding 不走这条路径。
- 若 AstrBot 用 Ollama 作为**对话**后端，则同样受影响，按第四节修。

## 八、诊断方法留档（下次复用）

1. 让 ollama 带 `OLLAMA_DEBUG=1` 在**独立端口**起一个实例，避免动到在用的服务。
2. 看日志里 llama-server 的**完整启动命令**（`msg="starting llama-server" cmd="..."`）—— 
   `--flash-attn auto` 就是线索。
3. 看崩溃点是不是 `cudaFuncSetAttribute`/`cudaFuncGetAttributes`（共享内存相关），
   而不是 `out of memory`。
4. 用 `OLLAMA_FLASH_ATTENTION=0` 验证：日志里应变成 `--flash-attn off`。
5. 清理测试实例：**按端口定位 PID**（`Get-NetTCPConnection -LocalPort <port>`），不要按名字批量杀。
