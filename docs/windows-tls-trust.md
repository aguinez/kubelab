# Configurar confianza TLS en Windows (browser)

Guía para que Chrome/Edge confíen en los certificados `*.lab.test` emitidos
por la CA interna del laboratorio (`lab-root-ca`).

---

## Resumen (lo esencial)

1. Exportar la CA interna del cluster → `lab-ca.crt`
2. Instalar la CA en el trust store de Windows (`LocalMachine\Root`)
3. Asegurarse de que los Certificates de los Ingress tengan `commonName`
   (sin él, el subject queda vacío y Chrome rechaza la cadena)
4. Cerrar y reabrir el browser (Chrome cachea las decisiones TLS)

---

## 1. Exportar la CA interna

Desde WSL (ya existe en el repo):

```bash
kubectl get secret lab-root-ca-tls -n cert-manager -o jsonpath='{.data.tls\.crt}' \
  | base64 -d > lab-ca.crt

# verificar
openssl x509 -in lab-ca.crt -noout -subject -issuer
# subject=CN = lab-root-ca
```

---

## 2. Instalar la CA en el trust store de Windows

### Opción A — automática desde WSL (con UAC)

```bash
# Copiar el cert a una ruta Windows visible para procesos elevados
powershell.exe -NoProfile -Command "
New-Item -ItemType Directory -Force -Path 'C:\Temp' | Out-Null
Copy-Item '\\wsl.localhost\ubuntu\home\aguinez\projects\kubelab\lab-ca.crt' 'C:\Temp\lab-ca.crt' -Force
"

# Instalar en LocalMachine\Root (pedirá confirmación UAC)
powershell.exe -NoProfile -Command "
\$script = 'certutil -addstore -f Root C:\Temp\lab-ca.crt'
Start-Process cmd -Verb RunAs -Wait -ArgumentList '/c', \$script
"
```

### Opción B — manual desde Windows

1. Abrir `lab-ca.crt` (doble clic) → **Instalar certificado...**
2. Seleccionar **Máquina local** → Siguiente
3. **Colocar todos los certificados en el siguiente almacén** → Examinar →
   **Entidades de certificación raíz de confianza** → Aceptar → Siguiente → Finalizar

### Opción C — desde PowerShell de Windows (admin)

```powershell
certutil -user -addstore Root C:\Temp\lab-ca.crt
```

### Verificar la instalación

```bash
powershell.exe -NoProfile -Command "
Get-ChildItem Cert:\LocalMachine\Root | Where-Object { \$_.Subject -like '*lab-root-ca*' } |
  Select-Object Subject, Thumbprint | Format-List
"
# Subject    : CN=lab-root-ca
# Thumbprint : 06AA6E1201EF59D0FD06C994D114E5B2BD2F0A35
```

El thumbprint debe coincidir con el de `lab-ca.crt`:

```bash
openssl x509 -in lab-ca.crt -noout -fingerprint -sha1
```

---

## 3. Los certificados de los Ingress deben tener commonName

**Síntoma:** Chrome da aviso "NET::ERR_CERT_INVALID" aunque la CA esté
instalada. El certificado servido tiene `subject=` **vacío** (solo SANs).

**Causa:** el `Certificate` de cert-manager no definía `commonName`, y el
issuer CA emite sin subject. Chrome/Edge rechazan certificados sin CN.

**Verificación:**
```bash
echo | openssl s_client -connect localhost:443 -servername argocd.lab.test 2>/dev/null \
  | openssl x509 -noout -subject -issuer
# subject=CN = argocd.lab.test   <- CORRECTO
# issuer=CN = lab-root-ca
```

**Fix:** definir `commonName` en cada `Certificate`:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: argocd-server-tls
  namespace: argocd
spec:
  secretName: argocd-server-tls
  commonName: argocd.lab.test      # <-- requerido
  dnsNames:
    - argocd.lab.test
  issuerRef:
    name: lab-issuer
    kind: ClusterIssuer
    group: cert-manager.io
```

Re-emitir borrando el secret (cert-manager regenera):

```bash
kubectl delete secret argocd-server-tls -n argocd
kubectl -n argocd wait --for=condition=Ready certificate/argocd-server-tls --timeout=60s
```

---

## 4. Cerrar Chrome por completo

Chrome cachea las decisiones de certificado y la lista de CAs. Tras instalar
la CA o reemitir certificados:

1. Cerrar **todas** las ventanas de Chrome (incluido el proceso de bandeja).
2. Opcional (más exhaustivo): terminar los procesos `chrome.exe` desde el
   Administrador de tareas.
3. Reabrir `https://argocd.lab.test`.

---

## 5. Verificación final

```bash
# Desde WSL: la cadena debe resolver contra la CA
echo | openssl s_client -connect localhost:443 -servername argocd.lab.test \
  -CAfile lab-ca.crt 2>/dev/null | grep 'Verify return code'

# Desde Windows: curl con el cert explícito (usa schannel/trust store)
powershell.exe -NoProfile -Command "
curl.exe -s -o NUL -w 'code=%{http_code}\n' \
  --cacert C:\Temp\lab-ca.crt \
  --connect-to argocd.lab.test:443:<IP-WSL>:443 \
  https://argocd.lab.test/
"
```

> Nota: `curl.exe` de Windows no siempre usa el trust store del sistema
> (depende de la build). La prueba **definitiva** es el browser: con la CA en
> `LocalMachine\Root` y el cert con commonName, Chrome no debe mostrar aviso.

---

## Troubleshooting

| Síntoma | Causa | Solución |
| ------- | ----- | -------- |
| `NET::ERR_CERT_AUTHORITY_INVALID` | CA no instalada | Pasos sección 2 |
| `NET::ERR_CERT_INVALID` con CA instalada | subject vacío (sin commonName) | Sección 3 |
| Sigue el aviso tras instalar la CA | Chrome cacheó la decisión | Sección 4 |
| `unable to verify the first certificate` (openssl) | nginx no envía la CA en la cadena | Normal; el trust store de Chrome completa la cadena con la CA instalada |
| `code=000` con curl.exe de Windows | curl no usa trust store / formato de `--resolve` | Usar `--cacert` o validar en el browser |

---

*Ver también: `docs/troubleshooting.md` y `docs/deployment-journal.md`.*
