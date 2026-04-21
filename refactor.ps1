$files = Get-ChildItem -Path . -Filter *.xaml -Recurse
$changedFilesCount = 0
$results = @()
foreach ($file in $files) {
    $content = [System.IO.File]::ReadAllText($file.FullName)
    $originalContent = $content
    $renames = [ordered]@{}
    $propertyMatches = [regex]::Matches($content, '<x:Property Name="([^"]+)" Type="([^"]+)"')
    foreach ($match in $propertyMatches) {
        $oldName = $match.Groups[1].Value
        $typeAttr = $match.Groups[2].Value
        if ($oldName -notmatch '^(in|out|io)_') {
            $prefix = ""
            if ($typeAttr -like "*InOutArgument(*") { $prefix = "io_" }
            elseif ($typeAttr -like "*OutArgument(*") { $prefix = "out_" }
            elseif ($typeAttr -like "*InArgument(*") { $prefix = "in_" }
            if ($prefix -ne "") {
                $newNameBase = $oldName
                if ($oldName -match '_') { $newNameBase = $oldName.Substring($oldName.IndexOf('_') + 1) }
                $newName = $prefix + $newNameBase
                if ($newName -ne $oldName) { $renames[$oldName] = $newName }
            }
        }
    }
    $variableMatches = [regex]::Matches($content, '<Variable [^>]*Name="([^"]+)"')
    foreach ($match in $variableMatches) {
        $oldName = $match.Groups[1].Value
        if ($oldName -match '_') {
            $newName = $oldName -replace '_', ''
            if ($newName -ne $oldName) { $renames[$oldName] = $newName }
        }
    }
    if ($renames.Count -gt 0) {
        foreach ($old in $renames.Keys) {
            $new = $renames[$old]
            $content = $content -replace "\b$([regex]::Escape($old))\b", $new
        }
        if ($content -ne $originalContent) {
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($file.FullName, $content, $utf8NoBom)
            $changedFilesCount++
            $fileRenames = @()
            $renames.Keys | Select-Object -First 10 | ForEach-Object { $fileRenames += "$_ -> $($renames[$_])" }
            $results += [PSCustomObject]@{ Path = $file.FullName; Renames = $fileRenames }
        }
    }
}
Write-Host "Number of changed files: $changedFilesCount"
foreach ($res in $results) {
    Write-Host "`nFile: $($res.Path)"
    foreach ($rn in $res.Renames) { Write-Host "  $rn" }
}
