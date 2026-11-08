# KubeBlocks (operador)

Operador de datos cloud-native que gestiona cargas como RustFS y las bases de
datos del ecosistema.

## Instalación GitOps

Dos Applications (`gitops/apps/kubeblocks.yaml`), ordenadas por `sync-wave`:

1. `kubeblocks-crds` (wave -3): aplica `crds/kubeblocks_crds.yaml`, vendorizado
   desde el release oficial **v1.1.0-beta.13**. El chart Helm no incluye los
   CRDs, por eso se aplican aparte (con `ServerSideApply` y `prune: false`).

> **Memoria de ArgoCD.** El bundle original son ~11 MB y hacer que
> `kustomize build` lo procese con el límite por defecto de 128 Mi tumba el
> `repo-server` (OOMKilled). Por eso:
> - los CRDs se guardan sin campos `description` (~3.5 MB), que solo son
>   documentación del schema;
> - el `repo-server` debe tener al menos **1 Gi** de límite de memoria.
>   El valor aplicado vive en `platform/argocd/argocd-Application.yaml`
>   (`repoServer.resources`); si ArgoCD se instaló desde el `Makefile`, añade
>   ese límite al `helm upgrade`.
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
