# KubeBlocks (operador)

Operador de datos cloud-native que gestiona cargas como RustFS y las bases de
datos del ecosistema.

## Instalación GitOps

Dos Applications (`gitops/apps/kubeblocks.yaml`), ordenadas por `sync-wave`:

1. `kubeblocks-crds` (wave -3): aplica `crds/kubeblocks_crds.yaml`, vendorizado
   desde el release oficial **v1.1.0-beta.13**. El chart Helm no incluye los
   CRDs, por eso se aplican aparte (con `ServerSideApply` y `prune: false`).
2. `kubeblocks` (wave -2): chart `kubeblocks` 1.1.0-beta.13 con los valores de
   `values.yaml` (multi-source, `$values`).

## Versión y compatibilidad

* Operador: **1.1.0-beta.13**.
* Addon RustFS: **0.1.0** (usa `systemAccounts.passwordGenerationPolicy`, campo
  vigente hasta KubeBlocks 1.1).
* El registro por defecto del chart (Aliyun) no es alcanzable aquí; `values.yaml`
  fija Docker Hub para todas las imágenes.
* `dataProtection` está desactivado para no depender del snapshot-controller.
* `autoInstalledAddons: []` evita instalar addons de bases de datos que no se usan.
