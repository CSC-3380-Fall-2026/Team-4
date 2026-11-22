(() => {
    const logoutButton = document.querySelector("#temporary-logout");
    if (!logoutButton) {
        return;
    }

    logoutButton.addEventListener("click", () => {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("user_email");
        window.location.assign("/login");
    });
})();
