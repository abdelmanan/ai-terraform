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

    const status = ref("idle"); // idle | loading | success | error
    const errorMessage = ref("");
    const result = ref(null);

    async function submit() {
      if (!isFormValid.value || status.value === "loading") return;

      status.value = "loading";
      errorMessage.value = "";
      result.value = null;

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
      }
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
      submit,
      downloadUrl,
    };
  },
}).mount("#app");
