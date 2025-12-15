<#
.SYNOPSIS
  示例：PowerShell 注册全局热键 + 显示点击标记 + 执行鼠标点击
  1. 脚本启动时，注册 [Ctrl+Alt+R] 为热键。
  2. 当捕捉到该热键时，按脚本中配置的坐标顺序执行点击。
  3. 每次点击前，会先在屏幕上用无边框窗口显示一个数字标记。
  4. 读取/写入坐标配置到外部 JSON 文件（示例）。

  注意：此脚本仅展示思路，并非最终商用级实现。
#>

# ================ 0. 判断并自提权限(如果需要) ================
# 如果不需要管理员权限，可省略此步骤
# 当脚本本身需要“以管理员身份”运行时，可以判断并自己调用powershell提升
If (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
{
    Write-Host "当前非管理员权限，尝试自提权运行本脚本..."
    Start-Process powershell "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    return
}

# ================ 1. 准备鼠标操作相关的 .NET 类 (P/Invoke) ================
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class User32 {
    // 用于移动鼠标
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    // 用于模拟鼠标点击
    [DllImport("user32.dll")]
    public static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, int dwExtraInfo);

    // 常量：左右键按下/抬起
    public const int MOUSEEVENTF_LEFTDOWN   = 0x02;
    public const int MOUSEEVENTF_LEFTUP     = 0x04;
    public const int MOUSEEVENTF_RIGHTDOWN  = 0x08;
    public const int MOUSEEVENTF_RIGHTUP    = 0x10;

    public static void LeftClick() {
        mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);
        mouse_event(MOUSEEVENTF_LEFTUP,   0, 0, 0, 0);
    }

    public static void RightClick() {
        mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0);
        mouse_event(MOUSEEVENTF_RIGHTUP,   0, 0, 0, 0);
    }

    // 注册/注销热键 (全局)
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    // 获取消息(消息循环)
    [DllImport("user32.dll", CharSet=CharSet.Auto)]
    public static extern int GetMessage(out MSG lpMsg, IntPtr hWnd, uint wMsgFilterMin, uint wMsgFilterMax);

    [DllImport("user32.dll", CharSet=CharSet.Auto)]
    public static extern bool TranslateMessage([In] ref MSG lpMsg);

    [DllImport("user32.dll", CharSet=CharSet.Auto)]
    public static extern IntPtr DispatchMessage([In] ref MSG lpmsg);

    [StructLayout(LayoutKind.Sequential)]
    public struct MSG {
        public IntPtr hWnd;
        public uint message;
        public IntPtr wParam;
        public IntPtr lParam;
        public int time;
        public int pt_x;
        public int pt_y;
    }
}
"@

# ================ 2. 注册 Windows Form (用于显示数字标记) ================
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function ShowMarker {
    param(
        [int]$X,
        [int]$Y,
        [string]$LabelText
    )
    # 新建一个无边框、置顶的小 Form，放在 (X, Y) 附近显示。
    # 这里演示最简单的写法，你可自己调整Size、位置偏移、颜色等。
    $form = New-Object System.Windows.Forms.Form
    $form.FormBorderStyle = 'None'
    $form.StartPosition   = 'Manual'
    $form.TopMost         = $true
    $form.BackColor       = [System.Drawing.Color]::LightYellow
    $form.Opacity         = 0.8
    $form.ShowInTaskbar   = $false

    # 尺寸和定位
    $markerSize = 50
    $form.Size       = [System.Drawing.Size]::new($markerSize,$markerSize)
    # 让窗口中心对准鼠标坐标，或根据需求做些偏移
    $form.Location   = [System.Drawing.Point]::new($X - $markerSize/2, $Y - $markerSize/2)

    # Label 文字
    $label = New-Object System.Windows.Forms.Label
    $label.Text      = $LabelText
    $label.AutoSize  = $true
    $label.Font      = New-Object System.Drawing.Font("Microsoft Sans Serif", 16,[System.Drawing.FontStyle]::Bold)
    $label.Location  = [System.Drawing.Point]::new(($markerSize - 20)/2,($markerSize - 30)/2)  # 简单让文字居中
    $form.Controls.Add($label)

    $form.Show()
    return $form
}

# ================ 3. 加载或初始化点击坐标配置 ================
# 这里演示用 JSON 文件来存坐标。比如:
# [
#   { "Index": 1, "X":100, "Y":200, "Type":"Right" },
#   { "Index": 2, "X":400, "Y":300, "Type":"Left"  }
# ]
# 当然也可改成 INI、XML 或 CSV。
$configPath = ".\mousePositions.json"
if (Test-Path $configPath) {
    $positions = Get-Content $configPath -Raw | ConvertFrom-Json
} else {
    # 默认初始化
    $positions = @(
        [pscustomobject]@{ Index=1; X=200; Y=200; Type="Right" },
        [pscustomobject]@{ Index=2; X=400; Y=300; Type="Left"  }
    )
    $positions | ConvertTo-Json | Out-File $configPath
}

Write-Host "当前点击坐标序列："
$positions | ForEach-Object {
    Write-Host "步骤 $_.Index => [$_.X, $_.Y], $_.Type Click"
}

# ================ 4. 定义 执行点击 的函数 ================
function PerformClicks {
    param([Object[]]$PosList)

    foreach ($p in $PosList) {
        # 1) 在屏幕上显示一个数字标记
        $labelForm = ShowMarker -X $p.X -Y $p.Y -LabelText ("{0}" -f $p.Index)

        # 2) 等待一下让用户看见
        Start-Sleep -Milliseconds 500

        # 3) 隐藏并释放标记
        $labelForm.Hide()
        $labelForm.Dispose()

        # 4) 移动并点击
        [User32]::SetCursorPos($p.X, $p.Y)
        switch ($p.Type.ToLower()) {
            "left"  { [User32]::LeftClick() }
            "right" { [User32]::RightClick() }
            default { [User32]::LeftClick() } # 默认左键
        }
        Start-Sleep -Milliseconds 200  # 两步之间稍作停顿
    }
}


# ================ 5. 注册全局热键 (Ctrl + Alt + R)  ================
# Win32 文档: RegisterHotKey(hwnd, id, fsModifiers, vk);
# 修饰键(Modifier)对应的数值：Alt=1, Ctrl=2, Shift=4, Win=8 (可相加)
# 这里我们使用 Alt+Ctrl = 1+2=3, 并且 VkKeyScan('R')=0x52(十六进制)
# 给它一个ID=0x9527(自定义)

$MOD_ALT  = 0x1
$MOD_CTRL = 0x2
$vk_R     = 0x52

$idHotKey = 0x9527

# RegisterHotKey 第一个参数 hWnd 我们没有真正窗口，这里传 0(虽然官方文档不推荐，但在脚本中常见)
[void][User32]::RegisterHotKey([IntPtr]::Zero, $idHotKey, ($MOD_ALT -bor $MOD_CTRL), $vk_R)
Write-Host "已注册全局热键: Ctrl + Alt + R (id=0x$idHotKey)"

# ================ 6. 启动消息循环，监听热键触发 ================
Write-Host "`n开始进入消息循环，按 Ctrl + Alt + R 试试(或在另一个PowerShell窗口Kill本脚本)..."

# 警告：这段循环会“阻塞”，直到用户终止脚本。若要后台驻留，可改用Runspace或用别的方法。
# 这里只演示“就地循环”的做法。
while ($true) {
    $msg = New-Object "User32+MSG"

    # GetMessage捕获任何窗口消息, 包括我们注册的热键
    $r = [User32]::GetMessage([ref]$msg, [IntPtr]::Zero, 0, 0)
    if ($r -eq 0) {
        break  # WM_QUIT
    }
    else {
        [void][User32]::TranslateMessage([ref]$msg)
        [void][User32]::DispatchMessage([ref]$msg)

        # 检查messageID(如果就是我们的热键ID)
        # 我们注册的hotkey触发时, message=0x0312(注册热键消息)，
        # wParam会是我们当初设定的idHotKey。
        if ($msg.message -eq 0x0312) {
            $hotkeyId = $msg.wParam.ToInt32()
            if ($hotkeyId -eq $idHotKey) {
                Write-Host "检测到热键 Ctrl+Alt+R，开始执行点击..."
                PerformClicks -PosList $positions
                Write-Host "点击操作已完成。"
            }
        }
    }
}

# ================ 7. 脚本结束时要注销热键 ================
[User32]::UnregisterHotKey([IntPtr]::Zero, $idHotKey)
Write-Host "已注销全局热键，脚本退出。"
