# Instalación de macOS con doble clic

En GitHub Actions, descarga el artefacto final **native-installers**. Dentro está
`Mictlan-AgriXGBoost-installer-macos-native.zip`. Descomprímelo con Finder y abre
**Instalar Mictlan-AgriXGBoost.app** con doble clic.

La aplicación muestra una confirmación, ejecuta la instalación y ofrece abrir la
app al terminar. No requiere escribir comandos en Terminal ni tener Python
instalado previamente. Si falta el Python 3.12 oficial, usa el `.pkg` incluido y
macOS solicita la contraseña de administrador. La preparación de dependencias
requiere Internet. El registro de esta operación queda en
`~/Library/Logs/Mictlan-AgriXGBoost/installation.log`.

El archivo `.command` queda dentro del payload como alternativa de diagnóstico.
Su permiso de ejecución se conserva en los ZIP y utiliza explícitamente Python
3.12, sin depender del PATH de Finder ni del Python de las herramientas de Xcode.

## Firma y notarización en Actions

La compilación final de macOS debe ejecutarse en un runner de macOS. El workflow
`build-installers.yml` añade el job `finalize-macos` después de ensamblar los
paquetes. Este job crea el `.app`, firma el código anidado —incluido
`libomp.dylib`— y después firma el `.app`. Envía el paquete a Apple con
`notarytool`, exige el resultado `Accepted`, adjunta el ticket con `stapler` y
verifica el paquete con Gatekeeper antes de publicar el ZIP final.

Configura estos **Repository secrets** en GitHub → Settings → Secrets and
variables → Actions:

| Secreto | Contenido |
| --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | Certificado **Developer ID Application** y su clave privada, exportados juntos como `.p12` y codificados en base64 en una sola línea. |
| `MACOS_CERTIFICATE_PASSWORD` | Contraseña usada al exportar ese `.p12`. Usa una contraseña no vacía. |
| `MACOS_SIGNING_IDENTITY` | Nombre completo de la identidad, por ejemplo `Developer ID Application: Nombre (TEAMID)`. |
| `APPLE_ID` | Correo de la cuenta Apple autorizada para notarizar. |
| `APPLE_TEAM_ID` | Identificador del equipo de Apple Developer. |
| `APPLE_APP_SPECIFIC_PASSWORD` | Contraseña específica de aplicación creada en la cuenta Apple para la notarización. |

El certificado requiere pertenecer al Apple Developer Program. Exporta el
certificado con su clave privada desde Acceso a Llaveros y guarda los valores
únicamente como secretos de GitHub; no los agregues al repositorio ni al `.env`
de la aplicación. El job usa un llavero temporal y lo elimina al terminar.

Sin secretos, Actions genera un `.app` **sin firma para desarrollo**, identificado
en `LEEME.txt` y en una advertencia del job. Esa versión puede seguir mostrando
los avisos de macOS: crear un `.app` o corregir el permiso del `.command` no
reemplaza la validación de Apple. Si se configura solo una parte de los secretos,
el job falla en vez de publicar silenciosamente un paquete sin firma.

Descarga **native-installers**, no `unsigned-native-installer-inputs`: el segundo
es un artefacto intermedio de ensamblado. Un ZIP anterior no adquiere la firma al
configurar los secretos; hay que ejecutar Actions y descargar el nuevo resultado.
macOS puede mostrar la confirmación normal de primera apertura y las solicitudes
de contraseña; el objetivo es evitar el aviso de software no verificable.

Para construir localmente en un Mac, a partir del ZIP nativo de ensamblado:

```bash
python3 installers/build_macos_app.py \
  --archive dist/Mictlan-AgriXGBoost-installer-macos-native.zip \
  --output dist/Mictlan-AgriXGBoost-installer-macos-native.zip \
  --identity 'Developer ID Application: Nombre (TEAMID)' \
  --profile mictlan-notary
```

El perfil `mictlan-notary` debe existir previamente en el llavero local mediante
`xcrun notarytool store-credentials`. Sin `--identity` y `--profile`, el comando
crea únicamente una compilación de desarrollo sin firma.

Referencias oficiales:
[Developer ID](https://developer.apple.com/developer-id/),
[notarización](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
[automatización con notarytool y stapler](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).
