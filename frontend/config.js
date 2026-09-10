// Configuration injectée à l'exécution, pas codée en dur dans app.js.
//
// Cette valeur est celle du développement local (./run.sh) : le frontend est
// servi par `python -m http.server` sur 5173, qui ne sait pas proxifier, donc
// le navigateur doit joindre uvicorn directement sur 8000.
//
// L'image Docker remplace ce fichier par une chaîne vide : nginx proxifie /api
// vers le backend, tout part de la même origine, et le frontend n'a plus besoin
// de connaître l'adresse du backend.
window.APP_CONFIG = { API_BASE: "http://127.0.0.1:8000" };
