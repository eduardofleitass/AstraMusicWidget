' Lanza el widget de musica sin abrir ninguna ventana de consola.
' Doble clic en este archivo, o usalo desde install_startup.bat para el arranque automatico.
Option Explicit
Dim fso, sh, here
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
Dim exe
exe = here & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(exe) Then
    MsgBox "No encuentro el entorno virtual:" & vbCrLf & exe & vbCrLf & vbCrLf & _
           "Ejecuta primero setup.bat", 16, "Widget de musica"
    WScript.Quit 1
End If
sh.Run """" & exe & """ """ & here & "\main.py""", 0, False
