(() => {
    // Submit the login and signup forms as JSON to their FastAPI endpoints.
    document.querySelectorAll("[data-auth-form]").forEach((form) => {
        form.addEventListener("submit", async (submitEvent) => {
            submitEvent.preventDefault();

            const formElement = submitEvent.currentTarget;
            const formData = new FormData(formElement);
            const message = formElement.querySelector("[data-auth-message]");
            const submitButton = formElement.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.textContent;
            const authType = formElement.dataset.authForm;

            message.textContent = "";
            message.className = "hidden rounded-md px-3 py-2 text-sm";
            submitButton.disabled = true;
            submitButton.textContent = authType === "login" ? "Logging in..." : "Creating account...";

            try {
                const response = await fetch(formElement.action, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body: JSON.stringify({
                        email: formData.get("email"),
                        password: formData.get("password"),
                    }),
                });
                const result = await response.json();

                if (!response.ok) {
                    const errorMessage = response.status === 422
                        ? "Enter a valid email address and password."
                        : result.detail || "Unable to complete your request. Please try again.";
                    throw new Error(errorMessage);
                }

                if (authType === "login") {
                    if (typeof result.access_token !== "string" || !result.access_token) {
                        throw new Error("Login succeeded, but no session token was returned.");
                    }
                    sessionStorage.setItem("access_token", result.access_token);
                    sessionStorage.setItem("user_email", String(formData.get("email")));
                    window.location.assign("/dashboard");
                    return;
                }

                message.textContent = result.confirmation_required
                    ? "Your account was created. Check your email to confirm your address before logging in."
                    : "Your account was created. Email confirmation is not required; you can log in now.";
                message.classList.add("bg-purple-50", "text-purple-700");
                formElement.reset();
            } catch (error) {
                message.textContent = error instanceof Error
                    ? error.message
                    : "Unable to complete your request. Please try again.";
                message.classList.add("bg-red-50", "text-red-700");
            } finally {
                message.classList.remove("hidden");
                submitButton.disabled = false;
                submitButton.textContent = originalButtonText;
            }
        });
    });
})();
