# 使用Windows内置System.Drawing把与SVG同源的场景渲染为PNG。
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$scenePath = Join-Path $PSScriptRoot 'er-assets/scene.json'
$outputPath = Join-Path $PSScriptRoot 'ER图_总览.png'
$scene = Get-Content -LiteralPath $scenePath -Raw -Encoding utf8 | ConvertFrom-Json
$bitmap = [System.Drawing.Bitmap]::new(1800,1430)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
try {
  foreach ($op in $scene) {
    if ($op.kind -eq 'rect') {
      $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($op.fill))
      $pen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($op.stroke),1)
      try {
        $graphics.FillRectangle($brush,[single]$op.x,[single]$op.y,[single]$op.w,[single]$op.h)
        $graphics.DrawRectangle($pen,[single]$op.x,[single]$op.y,[single]$op.w,[single]$op.h)
      } finally { $brush.Dispose(); $pen.Dispose() }
    } elseif ($op.kind -eq 'text') {
      $style = [System.Drawing.FontStyle]::Regular
      if ($op.weight -eq 'bold') { $style = [System.Drawing.FontStyle]::Bold }
      $font = [System.Drawing.Font]::new([string]$op.family,[single]$op.size,$style,[System.Drawing.GraphicsUnit]::Pixel)
      $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($op.color))
      try { $graphics.DrawString([string]$op.value,$font,$brush,[single]$op.x,[single]$op.y) }
      finally { $font.Dispose(); $brush.Dispose() }
    } elseif ($op.kind -eq 'line') {
      $pen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($op.color),[single]$op.width)
      try {
        for ($i=0; $i -lt $op.points.Count-1; $i++) {
          $graphics.DrawLine($pen,[single]$op.points[$i][0],[single]$op.points[$i][1],[single]$op.points[$i+1][0],[single]$op.points[$i+1][1])
        }
      } finally { $pen.Dispose() }
    }
  }
  $bitmap.Save($outputPath,[System.Drawing.Imaging.ImageFormat]::Png)
} finally { $graphics.Dispose(); $bitmap.Dispose() }
Write-Output "Rendered $outputPath"
