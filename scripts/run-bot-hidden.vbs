' Запуск бота без окна консоли.
' Планировщик заданий запускает этот файл через wscript.exe, а он уже
' вызывает run-bot.cmd в скрытом режиме (0 = без окна).
Dim fso, shell, folder, target
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
target = folder & "\run-bot.cmd"
shell.Run """" & target & """", 0, False
