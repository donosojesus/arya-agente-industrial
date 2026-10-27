# Parte III · Construir el ecosistema

El agente de la Parte II consulta una planta, un gateway y un CMMS que ya estaban funcionando. Esta parte abre esas cajas: cómo se simula una planta creíble, cómo se publica por OPC UA, cómo se construye una puerta de solo lectura y cómo se despliega todo sin Internet. El CMMS y sus credenciales se explicaron con la aprobación humana, en el capítulo 15.

| Capítulo | Qué construye |
|---|---|
| 18 · La planta simulada | Una bomba con señales correlacionadas, alarmas con histéresis y fallas de causa oculta, publicada por OPC UA |
| 19 · El gateway OT y el historian | La única puerta entre la planta y la IA: lee por OPC UA, guarda la historia y solo acepta lecturas |
| 20 · Despliegue sin Internet | Seis contenedores, actualizaciones sin red y un chequeo previo |
