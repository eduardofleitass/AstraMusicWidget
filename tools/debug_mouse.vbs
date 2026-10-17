' Arranca el widget con el registro de entrada de mouse activado.
' Sirve para depurar el mouse (hover, botones, barra de progreso): cada mensaje
' queda anotado en widget.log con sus coordenadas y el resultado del analisis de
' zonas. Sin esto no se ve si un clic llego a la ventana.
Option Explicit
Dim fso, sh, here, exe
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
sh.CurrentDirectory = here
exe = here & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(exe) Then
    MsgBox "No encuentro el entorno virtual:" & vbCrLf & exe, 16, "Widget de musica"
    WScript.Quit 1
End If
sh.Environment("Process")("GORUS_DEBUG_MOUSE") = "1"
sh.Run """" & exe & """ """ & here & "\main.py""", 0, False
