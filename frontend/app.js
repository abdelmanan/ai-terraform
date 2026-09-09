const API_BASE = "http://127.0.0.1:8000";

const PROJECT_NAME_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/;

const { createApp, reactive, ref, computed } = Vue;

createApp({
  setup() {
    const form = reactive({
      cloud: "aws",
      project_name: "",
      region: "eu-west-1",
      template: "landing-zone",
      availability_zones: 2,
      public_subnets: 2,
      private_subnets: 2,
      enable_nat_gateway: true,
      enable_cloudtrail: true,
      enable_cloudwatch: true,
      enable_s3_logs: true,
    });

    const projectNameError = computed(() => {
      if (!form.project_name) return null;
      if (!PROJECT_NAME_PATTERN.test(form.project_name)) {
        return "Lettres, chiffres, tirets et underscores uniquement (max 63 caractères, doit commencer par une lettre ou un chiffre).";
      }
      return null;
    });

    const isFormValid = computed(() => {
      return (
        form.project_name.trim().length > 0 &&
        !projectNameError.value &&
        form.region.trim().length > 0
      );
    });

    // The banner said "terraform validate: échec" whatever the step, so an
    // init timeout — which says nothing about the generated HCL — read as
    // broken code. The backend already reports where it stopped.
    const VALIDATION_LABELS = {
      validate: "✕ terraform validate : le code généré contient des erreurs",
      init: "✕ terraform init : la préparation du projet a échoué, le code n'a pas été vérifié",
      error: "✕ Terraform n'a pas pu être exécuté, le code n'a pas été vérifié",
      skipped: "✕ Validation ignorée : des fichiers essentiels sont manquants",
    };

    // The API answers in English, as an API should. Translating belongs here,
    // in the layer that owns the user's language. Anything unknown is shown
    // verbatim rather than swallowed: an untranslated warning still beats a
    // missing one.
    const WARNING_LABELS = [
      [/missing some expected files: (.+)$/,
        (m) => `Le modèle n'a pas produit tous les fichiers attendus : ${m[1]}`],
      [/cut off at the (\d+) token limit/,
        (m) => `La réponse du modèle a été coupée à la limite de ${m[1]} tokens : les fichiers générés sont probablement incomplets.`],
      [/^Self-repair attempt (\d+) failed: (.+)$/,
        (m) => `La tentative de réparation ${m[1]} n'a pas pu aboutir : ${m[2]}`],
      [/made the project worse/,
        () => "Une réparation a dégradé le projet : la meilleure version produite a été conservée."],
      [/(\d+) self-repair attempt\(s\) fixed the project/,
        (m) => `Le code généré était invalide ; ${m[1]} réparation(s) automatique(s) l'ont corrigé.`],
      [/(\d+) self-repair attempt\(s\) did not fix it/,
        (m) => `Le code généré était invalide ; ${m[1]} réparation(s) automatique(s) n'ont pas suffi. Les erreurs restantes sont détaillées ci-dessous.`],
      [/could not be archived for download: (.+)$/,
        (m) => `Le projet n'a pas pu être archivé pour le téléchargement : ${m[1]}. Les fichiers restent sur le serveur.`],
    ];

    function warningLabel(warning) {
      for (const [pattern, format] of WARNING_LABELS) {
        const match = warning.match(pattern);
        if (match) return format(match);
      }
      return warning;
    }

    // Terraform frames its errors in box-drawing characters, which `-no-color`
    // does not remove. Dumped raw, one "Unsupported argument" hid inside forty
    // lines of │ and ╵ and nobody read it.
    function parseTerraformErrors(stderr) {
      if (!stderr) return [];

      const errors = [];
      let current = null;

      for (const rawLine of stderr.split("\n")) {
        let line = rawLine.trim();

        if (line === "\u2577" || line === "\u2575") continue;
        if (line.startsWith("\u2502")) line = line.slice(1).trim();

        if (line.startsWith("Error:")) {
          if (current) errors.push(current);
          current = { title: line.slice(6).trim(), location: "", detail: [] };
          continue;
        }

        if (!current) continue;

        const at = line.match(/^on (.+?) line (\d+)(?:, in (.+))?:$/);
        if (at) {
          current.location = at[3]
            ? `${at[1]}, ligne ${at[2]} — ${at[3]}`
            : `${at[1]}, ligne ${at[2]}`;
          continue;
        }

        // The echoed source line ("12:   vpc = true") is already covered by
        // the location, and blank lines are only box padding.
        if (line === "" || /^\d+:/.test(line)) continue;

        current.detail.push(line);
      }

      if (current) errors.push(current);

      return errors.map((error) => ({
        title: error.title,
        location: error.location,
        detail: error.detail.join(" "),
      }));
    }

    const status = ref("idle"); // idle | loading | success | error
    const errorMessage = ref("");
    const result = ref(null);

    // A run can take several minutes: three model calls and three
    // init/validate cycles when both repairs fire. With a bare spinner and no
    // elapsed time, a working generation looks frozen and gets reloaded away.
    const elapsedSeconds = ref(0);
    let elapsedTimer = null;

    const loadingHint = computed(() => {
      if (elapsedSeconds.value < 45) {
        return "Appel du modèle IA, puis validation Terraform (init + validate).";
      }
      if (elapsedSeconds.value < 120) {
        return "Validation Terraform en cours — le téléchargement des providers peut être long au premier lancement.";
      }
      return "Le code généré était probablement invalide : une réparation automatique est en cours. C'est normal, laisse tourner.";
    });

    function startTimer() {
      elapsedSeconds.value = 0;
      elapsedTimer = setInterval(() => { elapsedSeconds.value += 1; }, 1000);
    }

    function stopTimer() {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }

    const terraformErrors = computed(() => {
      if (!result.value) return [];
      return parseTerraformErrors(result.value.validation.stderr);
    });

    async function submit() {
      if (!isFormValid.value || status.value === "loading") return;

      status.value = "loading";
      errorMessage.value = "";
      result.value = null;
      startTimer();

      try {
        const response = await fetch(`${API_BASE}/api/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        });

        const body = await response.json();

        if (!response.ok || body.status === "error") {
          errorMessage.value = body.message || "Une erreur est survenue.";
          status.value = "error";
          return;
        }

        result.value = body;
        status.value = "success";
      } catch (err) {
        errorMessage.value =
          "Impossible de contacter le serveur (" + err.message + "). Vérifie que le backend tourne sur " + API_BASE + ".";
        status.value = "error";
      } finally {
        stopTimer();
      }
    }

    function validationLabel() {
      if (!result.value) return "";

      const validation = result.value.validation;

      if (validation.valid) return "✓ terraform validate : OK";

      return VALIDATION_LABELS[validation.step] || VALIDATION_LABELS.error;
    }

    function downloadUrl() {
      if (!result.value) return "#";
      return `${API_BASE}${result.value.download}`;
    }

    return {
      form,
      projectNameError,
      isFormValid,
      status,
      errorMessage,
      result,
      elapsedSeconds,
      loadingHint,
      terraformErrors,
      validationLabel,
      warningLabel,
      submit,
      downloadUrl,
    };
  },
}).mount("#app");
