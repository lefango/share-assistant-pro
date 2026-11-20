$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
function Save-Lnk($Path, $Target, $Workdir, $Desc) {
    $sc = $ws.CreateShortcut($Path)
    $sc.TargetPath = $Target
    $sc.WorkingDirectory = $Workdir
    $sc.Description = $Desc
    $sc.Save()
}
$target = 'D:\software\ai\dpakzhinnegtibenti\ai工作区\分享助手\分享助手Pro\_work\installed\分享助手Pro.exe'
$workdir = 'D:\software\ai\dpakzhinnegtibenti\ai工作区\分享助手\分享助手Pro\_work\installed'
$desc = '分享助手 Pro'
$startMenu = [Environment]::GetFolderPath('Programs')
$dir = Join-Path $startMenu '分享助手Pro'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Save-Lnk (Join-Path $dir '分享助手Pro.lnk') $target $workdir $desc

