(() => {
    const emailLabel = document.querySelector("#profile-email");
    const email = sessionStorage.getItem("user_email");

    if (emailLabel && email) {
        emailLabel.textContent = email;
    }
})();
