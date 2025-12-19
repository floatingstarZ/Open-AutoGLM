# 排查 current_app 始终显示 "System Home" 的问题

如果您在 trace 日志中发现 `current_app` 字段始终显示为 "System Home"，而不是实际的应用名称，请按照以下步骤排查和解决。

## 问题原因

`current_app` 字段由 `get_current_app()` 函数获取，该函数通过以下方式检测当前运行的应用：

- **Android (ADB)**: 运行 `adb shell dumpsys window` 并解析输出
- **HarmonyOS (HDC)**: 运行 `hdc shell hidumper -s WindowManagerService` 并解析输出

如果始终返回 "System Home"，可能的原因包括：

1. ADB/HDC 命令执行失败
2. 系统输出格式与预期不符
3. 应用包名不在已知应用列表中（已修复）
4. 权限问题

## 快速诊断

### 步骤 1: 使用调试工具

我们提供了一个调试工具来帮助诊断问题：

```bash
# Android (ADB)
python scripts/debug_current_app.py adb

# HarmonyOS (HDC)
python scripts/debug_current_app.py hdc

# 指定设备 ID
python scripts/debug_current_app.py adb emulator-5554
```

### 步骤 2: 查看输出

调试工具会显示：

1. **命令是否执行成功**
2. **原始输出中是否包含焦点信息**
3. **提取的包名/bundle名是否正确**

**正常输出示例**：

```
==============================================================
Debugging ADB Current App Detection
==============================================================

[1] Running: adb shell dumpsys window...

[2] Looking for mCurrentFocus or mFocusedApp...
✅ Found 1 focus line(s):
--------------------------------------------------------------
mCurrentFocus=Window{abc123 u0 com.sankuai.meituan/com.sankuai.meituan.MainActivity}
--------------------------------------------------------------

[3] Extracting package name...
✅ Extracted package: com.sankuai.meituan

==============================================================
✅ Final result: com.sankuai.meituan
==============================================================
```

**异常输出示例**：

```
==============================================================
Debugging ADB Current App Detection
==============================================================

[1] Running: adb shell dumpsys window...

[2] Looking for mCurrentFocus or mFocusedApp...
❌ No focus information found!

Showing first 50 lines of output:
--------------------------------------------------------------
1: (输出内容)
...
==============================================================
❌ Could not detect current app
==============================================================
```

## 解决方案

### 方案 1: 检查 ADB/HDC 连接

```bash
# 检查设备是否连接
adb devices
# 或
hdc list targets

# 尝试手动运行命令
adb shell dumpsys window | grep mCurrentFocus
# 或
hdc shell hidumper -s WindowManagerService -a -a
```

### 方案 2: 更新代码（已修复）

最新版本的代码已经改进了 `get_current_app()` 函数：

- **以前**: 只能识别已知应用（在 `APP_PACKAGES` 中），其他应用返回 "System Home"
- **现在**: 即使应用不在已知列表中，也会返回实际的包名

确保您使用的是最新版本的代码。

### 方案 3: 检查权限

某些 Android 系统可能需要额外的权限才能获取窗口信息：

```bash
# 授予必要的权限（如果需要）
adb shell pm grant com.android.shell android.permission.DUMP
```

### 方案 4: 手动测试

在应用运行时手动测试：

```bash
# 1. 打开应用（例如：美团）
adb shell monkey -p com.sankuai.meituan 1

# 2. 等待 2 秒

# 3. 检查当前应用
adb shell dumpsys window | grep mCurrentFocus
```

**预期输出**：
```
mCurrentFocus=Window{... com.sankuai.meituan/...}
```

如果看到了正确的包名，说明 ADB 命令本身没问题。

### 方案 5: 检查编码问题

如果输出中包含乱码，可能是编码问题：

```python
# 在 phone_agent/adb/device.py 中
# 已经使用 encoding="utf-8"
result = subprocess.run(
    adb_prefix + ["shell", "dumpsys", "window"],
    capture_output=True,
    text=True,
    encoding="utf-8"  # 确保使用 UTF-8
)
```

## 验证修复

修复后，重新运行任务并检查 trace 日志：

```bash
# 运行任务
python main.py "打开美团"

# 查看最新的 trace
cat traces/task_xxx/trace.jsonl | jq '.current_app'
```

**预期输出**：
```json
"美团"
"com.sankuai.meituan"
"System Home"  # 只有在主屏幕时才应该出现
```

## 常见问题

### Q1: 为什么有时是应用名，有时是包名？

**A**: 代码会优先返回友好的应用名（如 "美团"），如果应用不在已知列表中，则返回包名（如 "com.example.app"）。

### Q2: 如何添加更多已知应用？

**A**: 编辑 `phone_agent/config/apps.py` (Android) 或 `phone_agent/config/apps_harmonyos.py` (HarmonyOS)：

```python
APP_PACKAGES = {
    "美团": "com.sankuai.meituan",
    "您的应用": "com.example.yourapp",  # 添加这行
    # ...
}
```

### Q3: 调试工具显示正确，但 trace 仍然是 "System Home"？

**A**: 可能是时序问题。`get_current_app()` 在截图后立即调用，如果应用切换很快，可能还没来得及更新。

解决方法：在 `agent.py` 中添加小延迟（已在最新代码中）。

## 技术细节

### 代码改进

**修复前** (`phone_agent/adb/device.py:12-38`)：

```python
def get_current_app(device_id: str | None = None) -> str:
    # ... 获取 dumpsys 输出 ...

    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"  # ❌ 直接返回默认值
```

**修复后** (`phone_agent/adb/device.py:12-58`)：

```python
def get_current_app(device_id: str | None = None) -> str:
    # ... 获取 dumpsys 输出 ...

    current_package = None
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            # 优先匹配已知应用
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

            # ✅ 提取实际包名
            import re
            match = re.search(r'([a-z][a-z0-9_]*(\.[a-z0-9_]+)+)', line)
            if match:
                current_package = match.group(1)
                break

    if current_package:
        return current_package  # ✅ 返回包名

    return "System Home"
```

## 获取帮助

如果问题仍未解决，请提供以下信息：

1. 调试工具的完整输出：`python scripts/debug_current_app.py adb > debug.log`
2. 手动运行命令的输出：`adb shell dumpsys window | grep mCurrentFocus > manual.log`
3. 系统信息：`adb shell getprop ro.build.version.release` (Android 版本)
4. Trace 日志片段

---

## 相关文档

- [trace_logger.py](../phone_agent/trace_logger.py) - Trace Logger 实现
- [TRACE_LOGGING.md](./TRACE_LOGGING.md) - Trace Logging 功能说明
- [debug_current_app.py](../scripts/debug_current_app.py) - 调试工具源码
