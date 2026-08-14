Option Explicit
Dim shell, fso, folder, pyw, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = ""
On Error Resume Next
pyw = shell.Exec("cmd /c where pythonw.exe").StdOut.ReadLine
On Error GoTo 0

If Len(Trim(pyw)) = 0 Then
    MsgBox "pythonw.exe nao foi encontrado. Execute CRIAR_SR_STUDIO_EXE.bat para criar o executavel.", 48, "SR Studio"
    WScript.Quit 1
End If

cmd = """" & Trim(pyw) & """ """ & folder & "\SR_Studio_Gerador.py"""
shell.Run cmd, 0, False
