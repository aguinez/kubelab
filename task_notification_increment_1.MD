una vez hecho lo de task_notification.MD

corresponde pasar de escribir el log a hacer una solicitud que levantará una nueva canalizacion de argo workflows

el primer paso de la canalizacion de argo workflows tomará el nombre de la application y deberá revisar los objetos dentro de la aplicación de argocd que está degradada o fallando para luego hacer consultas con kubectl para recolectar informacion de que es lo que está fallando (si es un pod o deployment hacer un get logs y un describe pod ejemplo para este caso).
de alguna forma reconocer la información relevante evitando acumular demasiadas veces el mismo error y preparar un request adicional con esa informacion hacia otro endpoint (aun no definido)


comienza creando la imagen de contenedor que recibirá el nombre de la application junto a su codigo
luego crea su deployment y su service de kubernetes
luego genera los RBAC necesarios para que las operaciones puedan llevarse a cabo dentro del mismo cluster de kubernetes
y finalmente crea el argo workflow y mete este ultimo deployment que ha sido creado como el primer paso de la orquestacion