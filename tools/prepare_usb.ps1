<#
.SYNOPSIS
  Prepare connected iPhones/iPads for wired casting (run as administrator).

.DESCRIPTION
  Wired casting uses libusb0 (libusb-win32) as the device's driver, the same
  setup TikTok LIVE Studio uses. For each connected Apple device this script:
    1. removes a libusb0 *filter* left on top of another driver
       (that combination can crash Windows with WDF_VIOLATION), and
    2. binds the libusb-win32 driver from the Windows driver store if the
       device is not already on it.
  It never touches non-Apple devices and makes no change when the device is
  already set up. Output is one line per device.
#>
param([switch]$Check)
$ErrorActionPreference = "Stop"

if ($Check) {
    # Exit 3 when a connected device still needs the driver, 0 otherwise.
    $pids = @("1290","1291","1292","1293","1294","1297","1299","129A","129C","129D","129E","129F",
              "12A0","12A1","12A2","12A3","12A4","12A5","12A6","12A8","12A9","12AA","12AB","12AC")
    foreach ($dev in @(Get-PnpDevice -PresentOnly)) {
        if ($dev.InstanceId -match '^USB\\VID_05AC&PID_([0-9A-F]{4})\\[^&\\]+$' -and $pids -contains $Matches[1]) {
            $p = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Enum\$($dev.InstanceId)"
            if ($p.Service -ne "libusb0" -or (@($p.UpperFilters) -contains "libusb0")) { exit 3 }
        }
    }
    exit 0
}

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Output "Not running as administrator; USB preparation skipped."
    exit 2
}

# Apple product IDs that expose the screen-capture configuration.
$CapturePids = @(
    "1290", "1291", "1292", "1293", "1294", "1297", "1299", "129A", "129C", "129D", "129E", "129F",
    "12A0", "12A1", "12A2", "12A3", "12A4", "12A5", "12A6", "12A8", "12A9", "12AA", "12AB", "12AC"
)

$devices = @(Get-PnpDevice -PresentOnly | Where-Object {
    $_.InstanceId -match '^USB\\VID_05AC&PID_([0-9A-F]{4})\\[^&\\]+$' -and $CapturePids -contains $Matches[1]
})
if (-not $devices) {
    Write-Output "No iPhone or iPad connected; nothing to prepare."
    exit 0
}

function Get-LibusbInf {
    $text = (pnputil /enum-drivers) -join "`n"
    foreach ($block in ($text -split "`n\s*`n")) {
        if ($block -match "Provider Name:\s+[^`n]*libusb-win32" -and $block -match "Published Name:\s+(\S+\.inf)") {
            return $Matches[1]
        }
    }
    return $null
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class NewDev {
    [DllImport("newdev.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool UpdateDriverForPlugAndPlayDevices(
        IntPtr hwndParent, string hardwareId, string fullInfPath, uint installFlags, out bool rebootRequired);
}
"@

foreach ($dev in $devices) {
    $key = "HKLM:\SYSTEM\CurrentControlSet\Enum\$($dev.InstanceId)"
    $props = Get-ItemProperty $key
    $changed = $false

    # 1. Drop a libusb0 filter (never keep libusb0 stacked on another driver).
    $filters = @($props.UpperFilters | Where-Object { $_ })
    if ($filters -contains "libusb0") {
        $rest = @($filters | Where-Object { $_ -ne "libusb0" })
        if ($rest.Count) {
            Set-ItemProperty $key -Name UpperFilters -Type MultiString -Value $rest
        } else {
            Remove-ItemProperty $key -Name UpperFilters
        }
        $changed = $true
        Write-Output "$($dev.FriendlyName): removed libusb0 filter."
    }

    # 2. Bind libusb-win32 as the device driver, as TikTok LIVE Studio does.
    if ($props.Service -ne "libusb0") {
        $inf = Get-LibusbInf
        if (-not $inf) {
            Write-Output "$($dev.FriendlyName): no libusb-win32 driver in the driver store. Install TikTok LIVE Studio's iOS driver once, then run Start.bat again."
            continue
        }
        $hwid = ($dev.InstanceId -split '\\')[0..1] -join '\'
        $reboot = $false
        if ([NewDev]::UpdateDriverForPlugAndPlayDevices([IntPtr]::Zero, $hwid, (Join-Path $env:WINDIR "INF\$inf"), 1, [ref]$reboot)) {
            Write-Output "$($dev.FriendlyName): bound libusb-win32 driver ($inf)."
            $changed = $false  # the driver install restarts the device itself
        } else {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            Write-Output "$($dev.FriendlyName): could not bind libusb-win32 driver (error $code)."
        }
    }

    if ($changed) {
        pnputil /restart-device "$($dev.InstanceId)" | Out-Null
    }
    if (-not $changed -and $props.Service -eq "libusb0" -and -not ($filters -contains "libusb0")) {
        Write-Output "$($dev.FriendlyName): ready."
    }
}
