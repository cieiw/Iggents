@echo off
setlocal EnableExtensions EnableDelayedExpansion
cls

:: ============================================================
:: USO:
::   limpeza_completa_android.bat SERIAL_DO_APARELHO
::
:: EXEMPLO:
::   limpeza_completa_android.bat RQCW309LXKL
:: ============================================================

set "DEVICE=%~1"

if "%DEVICE%"=="" (
    echo [X] ERRO: Voce precisa informar o SERIAL do aparelho.
    echo.
    echo Exemplo:
    echo limpeza_completa_android.bat RQCW309LXKL
    echo.
    exit /b 1
)

set /a OK_COUNT=0
set /a WARN_COUNT=0
set /a FAIL_COUNT=0

echo ============================================================
echo       LIMPEZA E VERIFICACAO COMPLETA DO ANDROID
echo ============================================================
echo Aparelho alvo: %DEVICE%
echo.

:: ------------------------------------------------------------
:: 1. VERIFICAR ADB E O DISPOSITIVO
:: ------------------------------------------------------------
where adb >nul 2>&1

if errorlevel 1 (
    echo [X] ERRO: O ADB nao foi encontrado no PATH.
    exit /b 1
)

set "ADB_STATE="

for /f "delims=" %%A in ('adb -s "%DEVICE%" get-state 2^>nul') do (
    set "ADB_STATE=%%A"
)

if /i not "!ADB_STATE!"=="device" (
    echo [X] ERRO: O aparelho "%DEVICE%" nao esta disponivel no ADB.
    echo.
    echo Verifique se:
    echo - o serial esta correto
    echo - o aparelho esta conectado
    echo - a depuracao USB esta autorizada
    echo.
    echo Dispositivos conectados:
    adb devices
    exit /b 1
)

echo [OK] Dispositivo encontrado e autorizado no ADB.
set /a OK_COUNT+=1
echo.

:: ------------------------------------------------------------
:: 2. IDENTIFICAR O APARELHO
:: ------------------------------------------------------------
set "MODEL="
set "BRAND="

for /f "delims=" %%A in ('adb -s "%DEVICE%" shell getprop ro.product.model 2^>nul') do (
    set "MODEL=%%A"
)

for /f "delims=" %%A in ('adb -s "%DEVICE%" shell getprop ro.product.brand 2^>nul') do (
    set "BRAND=%%A"
)

if not defined MODEL set "MODEL=Desconhecido"
if not defined BRAND set "BRAND=Desconhecida"

echo Marca : !BRAND!
echo Modelo: !MODEL!
echo Serial ADB: %DEVICE%
echo.

:: ------------------------------------------------------------
:: 3. VERIFICAR ROOT
:: ------------------------------------------------------------
set "HAS_ROOT=0"

adb -s "%DEVICE%" shell "su -c 'id'" 2>nul | findstr /c:"uid=0" >nul

if not errorlevel 1 (
    set "HAS_ROOT=1"
    echo [OK] Acesso Root confirmado.
    set /a OK_COUNT+=1
) else (
    echo [!] Dispositivo sem Root confirmado.
    echo     Etapas que exigem Root serao ignoradas ou poderao falhar.
    set /a WARN_COUNT+=1
)
echo.

:: ------------------------------------------------------------
:: 4. TENTAR APAGAR CHAVES DE IDENTIFICACAO
:: ------------------------------------------------------------
echo [1/11] Tentando apagar a chave Android ID...
call :DeleteSetting secure android_id "Android ID"
echo.

echo [2/11] Tentando apagar a chave advertising_id...
call :DeleteSetting secure advertising_id "Advertising ID"
echo.

echo [3/11] Tentando apagar a chave global device_id...
call :DeleteSetting global device_id "Device ID global"
echo.

:: ------------------------------------------------------------
:: 5. REINICIAR A INTERFACE WI-FI
:: ------------------------------------------------------------
echo [4/11] Tentando reiniciar a interface Wi-Fi...

set "WIFI_IFACE="

for /f "tokens=2 delims=: " %%A in ('adb -s "%DEVICE%" shell ip link 2^>nul ^| findstr /i "wlan wifi"') do (
    if not defined WIFI_IFACE (
        for /f "tokens=1 delims=@" %%B in ("%%A") do set "WIFI_IFACE=%%B"
    )
)

if not defined WIFI_IFACE (
    echo [!] AVISO: Nenhuma interface Wi-Fi foi localizada automaticamente.
    set /a WARN_COUNT+=1
) else (
    echo     Interface detectada: !WIFI_IFACE!

    set "MAC_BEFORE="
    for /f "delims=" %%A in ('adb -s "%DEVICE%" shell "cat /sys/class/net/!WIFI_IFACE!/address 2>/dev/null"') do (
        set "MAC_BEFORE=%%A"
    )

    if "!HAS_ROOT!"=="1" (
        adb -s "%DEVICE%" shell "su -c 'ip link set !WIFI_IFACE! down && sleep 2 && ip link set !WIFI_IFACE! up'" >nul 2>&1

        if errorlevel 1 (
            echo [X] FALHOU: O Android recusou o reinicio da interface Wi-Fi.
            set /a FAIL_COUNT+=1
        ) else (
            set "MAC_AFTER="
            for /f "delims=" %%A in ('adb -s "%DEVICE%" shell "cat /sys/class/net/!WIFI_IFACE!/address 2>/dev/null"') do (
                set "MAC_AFTER=%%A"
            )

            echo     MAC antes : !MAC_BEFORE!
            echo     MAC depois: !MAC_AFTER!

            if defined MAC_AFTER (
                echo [OK] Interface Wi-Fi reiniciada.
                set /a OK_COUNT+=1
            ) else (
                echo [X] FALHOU: Nao foi possivel validar a interface apos reiniciar.
                set /a FAIL_COUNT+=1
            )
        )
    ) else (
        echo [!] IGNORADO: O reinicio direto da interface Wi-Fi exige Root.
        set /a WARN_COUNT+=1
    )
)
echo.

:: ------------------------------------------------------------
:: 6. TENTAR ALTERAR O SERIAL INFORMADO PELO ANDROID
:: ------------------------------------------------------------
echo [5/11] Tentando alterar a propriedade ro.serialno...

set "CURRENT_SERIAL="
for /f "delims=" %%A in ('adb -s "%DEVICE%" shell getprop ro.serialno 2^>nul') do (
    set "CURRENT_SERIAL=%%A"
)

if not defined CURRENT_SERIAL set "CURRENT_SERIAL=nao informado"
echo     Serial atual: !CURRENT_SERIAL!

set "NEW_SERIAL="
for /f "delims=" %%A in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"') do (
    set "NEW_SERIAL=%%A"
)

if not defined NEW_SERIAL (
    echo [X] FALHOU: Nao foi possivel gerar um novo valor de serial.
    set /a FAIL_COUNT+=1
) else (
    set "SERIAL_TMP=%TEMP%\adb_serial_%RANDOM%_%RANDOM%.txt"

    if "!HAS_ROOT!"=="1" (
        adb -s "%DEVICE%" shell "su -c 'setprop ro.serialno !NEW_SERIAL!'" >"!SERIAL_TMP!" 2>&1
    ) else (
        adb -s "%DEVICE%" shell setprop ro.serialno !NEW_SERIAL! >"!SERIAL_TMP!" 2>&1
    )

    set "CHECK_SERIAL="
    for /f "delims=" %%A in ('adb -s "%DEVICE%" shell getprop ro.serialno 2^>nul') do (
        set "CHECK_SERIAL=%%A"
    )

    if /i "!CHECK_SERIAL!"=="!NEW_SERIAL!" (
        echo     Novo serial: !CHECK_SERIAL!
        echo [OK] Serial alterado e confirmado.
        set /a OK_COUNT+=1
    ) else (
        echo [X] FALHOU: O serial nao foi alterado.
        echo     Solicitado: !NEW_SERIAL!
        echo     Retornado : !CHECK_SERIAL!
        echo     A propriedade ro.serialno normalmente e somente leitura.
        set /a FAIL_COUNT+=1

        if exist "!SERIAL_TMP!" (
            for %%F in ("!SERIAL_TMP!") do (
                if %%~zF GTR 0 (
                    echo.
                    echo     Resposta do Android:
                    type "!SERIAL_TMP!"
                )
            )
        )
    )

    del "!SERIAL_TMP!" >nul 2>&1
)
echo.

:: ------------------------------------------------------------
:: 7. APAGAR CHAVES LEGADAS DE REDE
:: ------------------------------------------------------------
echo [6/11] Tentando apagar chaves legadas de rede...
call :DeleteSetting system wifi_ssid "wifi_ssid"
call :DeleteSetting system wifi_ip "wifi_ip"
echo [i] Essas chaves nao representam a lista real de redes Wi-Fi salvas.
echo.

:: ------------------------------------------------------------
:: 8. LIMPAR GOOGLE
:: ------------------------------------------------------------
echo [7/11] Limpando o aplicativo Google...
call :ClearPackage "com.google.android.googlequicksearchbox" "Google"
echo.

:: ------------------------------------------------------------
:: 9. LIMPAR GOOGLE CHROME
:: ------------------------------------------------------------
echo [8/11] Limpando o Google Chrome...
call :ClearPackage "com.android.chrome" "Google Chrome"
echo.

:: ------------------------------------------------------------
:: 10. LIMPAR GMAIL
:: ------------------------------------------------------------
echo [9/11] Limpando o Gmail...
call :ClearPackage "com.google.android.gm" "Gmail"
echo [i] Isso limpa os dados locais do Gmail, mas nao remove a Conta Google do Android.
echo.

:: ------------------------------------------------------------
:: 11. LIMPAR INSTAGRAM
:: ------------------------------------------------------------
echo [10/11] Limpando o Instagram...
call :ClearPackage "com.instagram.android" "Instagram"
echo.

:: ------------------------------------------------------------
:: 12. VERIFICAR COOKIES DO WEBVIEW DO INSTAGRAM
:: ------------------------------------------------------------
echo [11/11] Verificando cookies do WebView do Instagram...

adb -s "%DEVICE%" shell pm path com.instagram.android 2>nul | findstr /b /c:"package:" >nul

if errorlevel 1 (
    echo [!] IGNORADO: O Instagram nao esta instalado.
    set /a WARN_COUNT+=1
) else if "!HAS_ROOT!"=="1" (
    adb -s "%DEVICE%" shell "su -c 'rm -f /data/user/0/com.instagram.android/app_webview/Cookies* 2>/dev/null'" >nul 2>&1

    set "COOKIE_STATE="
    for /f "delims=" %%A in ('adb -s "%DEVICE%" shell "su -c 'ls /data/user/0/com.instagram.android/app_webview/Cookies* >/dev/null 2>&1 && echo FOUND || echo CLEAN'" 2^>nul') do (
        set "COOKIE_STATE=%%A"
    )

    if /i "!COOKIE_STATE!"=="CLEAN" (
        echo [OK] Nenhum arquivo Cookies foi encontrado.
        set /a OK_COUNT+=1
    ) else if /i "!COOKIE_STATE!"=="FOUND" (
        echo [X] FALHOU: Ainda existem arquivos Cookies no diretorio.
        set /a FAIL_COUNT+=1
    ) else (
        echo [X] FALHOU: Nao foi possivel confirmar o estado dos cookies.
        set /a FAIL_COUNT+=1
    )
) else (
    echo [!] VERIFICACAO PROFUNDA IGNORADA: O aparelho nao possui Root.
    echo [i] O comando pm clear ja remove os dados locais do Instagram.
    set /a WARN_COUNT+=1
)

:: ------------------------------------------------------------
:: 13. GARANTIR QUE OS APLICATIVOS FIQUEM ENCERRADOS
:: ------------------------------------------------------------
adb -s "%DEVICE%" shell am force-stop com.google.android.googlequicksearchbox >nul 2>&1
adb -s "%DEVICE%" shell am force-stop com.android.chrome >nul 2>&1
adb -s "%DEVICE%" shell am force-stop com.google.android.gm >nul 2>&1
adb -s "%DEVICE%" shell am force-stop com.instagram.android >nul 2>&1

echo.
echo ============================================================
echo                    RESULTADO FINAL
echo ============================================================
echo Aparelho : %DEVICE%
echo Marca    : !BRAND!
echo Modelo   : !MODEL!
echo Sucessos : !OK_COUNT!
echo Avisos   : !WARN_COUNT!
echo Falhas   : !FAIL_COUNT!
echo ============================================================
echo.

echo INFORMACOES IMPORTANTES SOBRE WI-FI:
echo - Reiniciar a interface causa uma desconexao temporaria.
echo - Isso nao apaga redes Wi-Fi salvas nem suas senhas.
echo - Isso nao garante a troca do endereco MAC.
echo - As chaves wifi_ssid e wifi_ip nao sao a lista real de redes salvas.
echo - Limpar Google ou Chrome nao remove as configuracoes Wi-Fi do Android.
echo.

if !FAIL_COUNT! GTR 0 (
    echo [X] O processo terminou com falhas.
    exit /b 2
)

if !WARN_COUNT! GTR 0 (
    echo [!] O processo terminou com avisos.
    exit /b 0
)

echo [OK] Todas as etapas executaveis foram confirmadas.
exit /b 0


:: ============================================================
:: FUNCAO: APAGAR E VERIFICAR UMA CONFIGURACAO
:: ============================================================
:DeleteSetting

set "SETTING_NAMESPACE=%~1"
set "SETTING_KEY=%~2"
set "SETTING_NAME=%~3"
set "SETTING_BEFORE="
set "SETTING_AFTER="
set "SETTING_BAD=0"

for /f "delims=" %%A in ('adb -s "%DEVICE%" shell settings get "!SETTING_NAMESPACE!" "!SETTING_KEY!" 2^>nul') do (
    set "SETTING_BEFORE=%%A"
)

if not defined SETTING_BEFORE set "SETTING_BEFORE=null"

set "SETTING_TMP=%TEMP%\adb_setting_%RANDOM%_%RANDOM%.txt"

adb -s "%DEVICE%" shell settings delete "!SETTING_NAMESPACE!" "!SETTING_KEY!" >"!SETTING_TMP!" 2>&1
set "SETTING_RC=!errorlevel!"

findstr /i /c:"Exception" /c:"Error" /c:"Permission denial" /c:"SecurityException" "!SETTING_TMP!" >nul
if not errorlevel 1 set "SETTING_BAD=1"
if not "!SETTING_RC!"=="0" set "SETTING_BAD=1"

for /f "delims=" %%A in ('adb -s "%DEVICE%" shell settings get "!SETTING_NAMESPACE!" "!SETTING_KEY!" 2^>nul') do (
    set "SETTING_AFTER=%%A"
)

if not defined SETTING_AFTER set "SETTING_AFTER=null"

echo     Antes : !SETTING_BEFORE!
echo     Depois: !SETTING_AFTER!

if "!SETTING_BAD!"=="1" (
    echo [X] FALHOU: O Android recusou a alteracao de !SETTING_NAME!.
    if exist "!SETTING_TMP!" type "!SETTING_TMP!"
    set /a FAIL_COUNT+=1
) else if /i "!SETTING_BEFORE!"=="null" (
    if /i "!SETTING_AFTER!"=="null" (
        echo [!] AVISO: !SETTING_NAME! ja nao existia nessa area.
        set /a WARN_COUNT+=1
    ) else (
        echo [!] AVISO: A configuracao foi recriada automaticamente.
        set /a WARN_COUNT+=1
    )
) else if /i "!SETTING_AFTER!"=="null" (
    echo [OK] !SETTING_NAME! apagado e confirmado.
    set /a OK_COUNT+=1
) else if /i not "!SETTING_BEFORE!"=="!SETTING_AFTER!" (
    echo [OK] !SETTING_NAME! mudou apos o comando.
    set /a OK_COUNT+=1
) else (
    echo [X] FALHOU: !SETTING_NAME! permaneceu igual.
    set /a FAIL_COUNT+=1
)

del "!SETTING_TMP!" >nul 2>&1
goto :eof


:: ============================================================
:: FUNCAO: LIMPAR E VERIFICAR UM PACOTE
:: ============================================================
:ClearPackage

set "PACKAGE_NAME=%~1"
set "APP_NAME=%~2"
set "CLEAR_SUCCESS=0"

adb -s "%DEVICE%" shell pm path "!PACKAGE_NAME!" 2>nul | findstr /b /c:"package:" >nul

if errorlevel 1 (
    echo [!] AVISO: !APP_NAME! nao esta instalado neste dispositivo.
    set /a WARN_COUNT+=1
    goto :eof
)

adb -s "%DEVICE%" shell am force-stop "!PACKAGE_NAME!" >nul 2>&1

set "CLEAR_TMP=%TEMP%\adb_clear_%RANDOM%_%RANDOM%.txt"

adb -s "%DEVICE%" shell pm clear "!PACKAGE_NAME!" >"!CLEAR_TMP!" 2>&1
set "CLEAR_RC=!errorlevel!"

findstr /i /c:"Success" "!CLEAR_TMP!" >nul
if not errorlevel 1 set "CLEAR_SUCCESS=1"

if "!CLEAR_RC!"=="0" if "!CLEAR_SUCCESS!"=="1" (
    echo [OK] Dados do !APP_NAME! apagados. O Android retornou Success.
    set /a OK_COUNT+=1
) else (
    echo [X] FALHOU: O Android nao confirmou a limpeza do !APP_NAME!.
    echo     Resposta:
    type "!CLEAR_TMP!"
    set /a FAIL_COUNT+=1
)

del "!CLEAR_TMP!" >nul 2>&1
goto :eof
