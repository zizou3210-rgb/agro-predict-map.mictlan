on run
    set payloadPath to POSIX path of (path to resource "payload")
    set homePath to POSIX path of (path to home folder)
    set logFolder to homePath & "Library/Logs/Mictlan-AgriXGBoost"
    set logPath to logFolder & "/installation.log"
    display dialog "Se instalará Mictlan-AgriXGBoost para tu usuario. La preparación puede tardar varios minutos y necesita Internet. Si falta Python 3.12, se solicitará tu contraseña para instalarlo." with title "Mictlan-AgriXGBoost" buttons {"Cancelar", "Instalar"} default button "Instalar" cancel button "Cancelar"
    try
        do shell script "/bin/mkdir -p " & quoted form of logFolder
        with timeout of 7200 seconds
            do shell script "/bin/bash " & quoted form of (payloadPath & "/Mictlan-AgriXGBoost_Installer.command") & " > " & quoted form of logPath & " 2>&1"
        end timeout
    on error errorMessage number errorNumber
        display dialog "No se pudo completar la instalación.\n\nRegistro: " & logPath & "\n\n" & errorMessage with title "Mictlan-AgriXGBoost" buttons {"Aceptar"} default button "Aceptar" with icon stop
        return
    end try
    set resultDialog to display dialog "Instalación completada. También encontrarás Mictlan-AgriXGBoost.command en tu Escritorio y en la carpeta Aplicaciones de tu usuario." with title "Mictlan-AgriXGBoost" buttons {"Cerrar", "Abrir aplicación"} default button "Abrir aplicación"
    if button returned of resultDialog is "Abrir aplicación" then
        do shell script "/usr/bin/open " & quoted form of (homePath & "Applications/Mictlan-AgriXGBoost.command")
    end if
end run
