# syntax=docker/dockerfile:1

# Le frontend est du HTML/CSS/JS statique : il n'a besoin ni de Python ni de
# Node, juste d'un serveur de fichiers — qui fait aussi office de proxy /api.
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html style.css app.js /usr/share/nginx/html/

# En conteneur, nginx proxifie /api : le frontend parle à sa propre origine.
# Cela écrase la valeur de développement de frontend/config.js.
RUN printf 'window.APP_CONFIG = { API_BASE: "" };\n' \
      > /usr/share/nginx/html/config.js

EXPOSE 80
