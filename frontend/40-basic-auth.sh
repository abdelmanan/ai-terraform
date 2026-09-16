#!/bin/sh
# Exécuté par l'entrypoint de l'image nginx avant le démarrage.
#
# Si BASIC_AUTH_USER et BASIC_AUTH_PASSWORD sont définis, tout le site (hors
# /health) exige une authentification. Sinon auth.conf reste vide et le site
# est ouvert — acceptable en local, pas sur une instance publique.
set -eu

AUTH_DIR=/etc/nginx/auth

if [ -n "${BASIC_AUTH_USER:-}" ] && [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
    # nginx accepte le schéma {PLAIN} : pas besoin d'htpasswd dans l'image.
    # Le fichier ne quitte jamais le conteneur.
    printf '%s:{PLAIN}%s\n' "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD" > "$AUTH_DIR/htpasswd"
    chmod 640 "$AUTH_DIR/htpasswd"
    chown root:nginx "$AUTH_DIR/htpasswd"

    printf 'auth_basic "AI Terraform Landing Zone Generator";\nauth_basic_user_file %s/htpasswd;\n' \
        "$AUTH_DIR" > "$AUTH_DIR/auth.conf"

    echo "40-basic-auth: authentification basique activée pour '$BASIC_AUTH_USER'"
else
    : > "$AUTH_DIR/auth.conf"
    echo "40-basic-auth: BASIC_AUTH_USER/BASIC_AUTH_PASSWORD absents, site sans authentification"
fi
