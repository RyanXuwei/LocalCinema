Option Explicit
Dim shell, shortcut, args
Set args = WScript.Arguments
If args.Count <> 4 Then WScript.Quit 2
Set shell = CreateObject("WScript.Shell")
Set shortcut = shell.CreateShortcut(args(2))
shortcut.TargetPath = args(0)
shortcut.Arguments = Chr(34) & args(1) & Chr(34)
shortcut.WorkingDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(args(1))
shortcut.IconLocation = args(3) & ",0"
shortcut.Description = "LocalCinema - by BitingBox Studio"
shortcut.Save
