apps/app_error_test_notification: este directorio debe contener un dockerfile, con una argocd application que apunte a este directorio y repositorio con su respectivo svc, deployment que falle tras una cantidad determinada de segundos (default 30).


apps/webhook: Este folder debe contener un dockerfile, el deployment, el svc de un webhook que pueda recibir e imprimir en su log el nombre de la aplicacion con problemas que viene desde notification controller de argocd


kubelab\platform\argocd : aqui debes crear el configmap o recursos de argocd que sean necesarios para configurar la notificacion.

Lo primero es crear la app que falle
despues el webhook
despues la notificacion