// ---------------------------------------------------------------- border
// AUTHENTICATION & LOGIN SUBSYSTEM (ISOLATED SCRIPT CONTEXT)
// ---------------------------------------------------------------- border

const API_URL = ""; 
let userToken = localStorage.getItem("token") || "";
let userRole = localStorage.getItem("role") || "";
let userFacultyId = localStorage.getItem("faculty_id") || "";

async function performLogin(usernameInput, passwordInput) {
    const errorDiv = document.getElementById("login-error");
    const submitBtn = document.getElementById("login-submit-btn");
    const originalBtnHtml = submitBtn ? submitBtn.innerHTML : "Sign In";
    
    if (errorDiv) errorDiv.classList.add("hidden");
    
    if (!usernameInput || !passwordInput) {
        const msg = "Please enter both username and password.";
        if (errorDiv) {
            errorDiv.innerText = msg;
            errorDiv.classList.remove("hidden");
        }
        if (typeof showToast === "function") showToast(msg, "error");
        return;
    }
    
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span><i class="fa-solid fa-spinner animate-spin mr-2"></i> Signing In...</span>`;
    }
    
    try {
        let res = await fetch(`${API_URL}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: usernameInput, password: passwordInput })
        });
        
        if (!res.ok && res.status === 404) {
            res = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: usernameInput, password: passwordInput })
            });
        }
        
        const responseText = await res.text();
        
        if (!res.ok) {
            let errMsg = `Invalid credentials (${res.status})`;
            try {
                const err = JSON.parse(responseText);
                errMsg = err.detail || errMsg;
            } catch (_) {
                errMsg = responseText.trim() || errMsg;
            }
            throw new Error(errMsg);
        }
        
        const data = JSON.parse(responseText);
        userToken = data.token;
        userRole = data.role;
        userFacultyId = data.faculty_id || "";
        
        localStorage.setItem("token", userToken);
        localStorage.setItem("role", userRole);
        localStorage.setItem("username", data.username);
        localStorage.setItem("faculty_id", userFacultyId);
        
        if (typeof showToast === "function") {
            showToast(`Welcome back, ${data.username}! Logged in successfully.`, "success");
        }
        if (typeof initApp === "function") {
            initApp();
        } else {
            window.location.reload();
        }
    } catch (err) {
        if (errorDiv) {
            errorDiv.innerText = err.message || "Login failed. Please check network connection.";
            errorDiv.classList.remove("hidden");
        }
        if (typeof showToast === "function") {
            showToast(`Login Failed: ${err.message || "Network error"}`, "error");
        }
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHtml;
        }
    }
}

async function handleLogin(e) {
    if (e && typeof e.preventDefault === "function") {
        e.preventDefault();
    }
    const usernameEl = document.getElementById("username");
    const passwordEl = document.getElementById("password");
    const usernameInput = usernameEl ? usernameEl.value.trim() : "";
    const passwordInput = passwordEl ? passwordEl.value.trim() : "";
    await performLogin(usernameInput, passwordInput);
    return false;
}

function handleLogout() {
    localStorage.clear();
    userToken = "";
    userRole = "";
    userFacultyId = "";
    window.location.reload();
}
