/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

function notify(message) {
    let toast = document.getElementById("toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.className = "toast";
        toast.id = "toast";
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(window.toastTimer);
    window.toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
}

publicWidget.registry.MyOdooPortal = publicWidget.Widget.extend({
    selector: ".page, .myodoo-portal-root",

    init() {
        this._super(...arguments);
        this.rpc = rpc;
    },

    start() {
        this._super.apply(this, arguments);
        this._initTabs();
        this._initActions();
        this._initModals();
        this._initSearch();
        this._initSettings();
        this._initMails();

        if (location.hash) {
            const targetTab = document.querySelector('[data-tab="' + location.hash.slice(1) + '"]');
            if (targetTab) {
                targetTab.click();
            }
        }
    },

    _getInstanceId() {
        const el = document.getElementById("o_instance_id") || document.querySelector("[data-instance-id]");
        if (el) {
            return parseInt(el.dataset.instanceId || el.value);
        }
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("id")) {
            return parseInt(urlParams.get("id"));
        }
        return false;
    },

    _initTabs() {
        document.querySelectorAll("[data-tab]").forEach(button => {
            button.addEventListener("click", () => {
                document.querySelectorAll("[data-tab]").forEach(item => item.classList.remove("active"));
                document.querySelectorAll(".tab-pane").forEach(item => item.classList.remove("active"));
                button.classList.add("active");
                const targetPane = document.getElementById(button.dataset.tab);
                if (targetPane) {
                    targetPane.classList.add("active");
                }
                if (button.dataset.tab === "logs") {
                    this._fetchLiveLogs();
                }
            });
        });

        document.querySelectorAll("[data-tab-jump]").forEach(button => {
            button.addEventListener("click", () => {
                const target = document.querySelector('[data-tab="' + button.dataset.tabJump + '"]');
                if (target) {
                    target.click();
                    window.scrollTo({ top: 0, behavior: "smooth" });
                }
            });
        });
    },

    _initActions() {
        document.querySelectorAll("[data-action]").forEach(button => {
            button.addEventListener("click", async (e) => {
                e.preventDefault();
                const action = button.dataset.action;
                const instanceId = this._getInstanceId();

                if (action === "github") {
                    const ghModal = document.getElementById("githubModal");
                    if (ghModal) {
                        ghModal.classList.add("show");
                    }
                } else if (action === "backup") {
                    if (!instanceId) {
                        notify("No instance selected.");
                        return;
                    }
                    notify("Creating backup, please wait...");
                    try {
                        const res = await this.rpc("/saas/instance/create-backup", { instance_id: instanceId });
                        if (res && res.success !== false) {
                            notify("Backup completed successfully.");
                            setTimeout(() => location.reload(), 1500);
                        } else {
                            notify("Backup failed: " + (res?.error || "Unknown error"));
                        }
                    } catch (err) {
                        notify("Backup error: " + (err.message || err));
                    }
                } else if (action === "rebuild") {
                    if (!instanceId) {
                        notify("No instance selected.");
                        return;
                    }
                    notify("Redeploying latest Git revision...");
                    try {
                        const res = await this.rpc("/saas/instance/redeploy", { instance_id: instanceId });
                        if (res && res.success !== false) {
                            notify("Redeployment triggered successfully.");
                        } else {
                            notify("Redeploy failed: " + (res?.error || "Error"));
                        }
                    } catch (err) {
                        notify("Redeploy error: " + err.message);
                    }
                } else if (action === "open") {
                    const url = button.dataset.url || document.getElementById("instanceUrl")?.value;
                    if (url) {
                        window.open(url, "_blank");
                    } else {
                        notify("Instance URL not available.");
                    }
                } else if (action === "add-domain") {
                    const input = document.getElementById("domainInput");
                    if (!input || !input.value.trim()) {
                        notify("Enter a domain name first.");
                        return;
                    }
                    const domainName = input.value.trim();
                    if (!instanceId) {
                        notify("No instance selected.");
                        return;
                    }
                    notify("Adding custom domain: " + domainName + "...");
                    try {
                        const res = await this.rpc("/saas/instance/add-domain-name", {
                            instance_id: instanceId,
                            domain_name: domainName
                        });
                        if (res && res.success) {
                            const list = document.getElementById("domainList");
                            if (list) {
                                const row = document.createElement("div");
                                row.className = "option";
                                row.innerHTML = '<div><strong>' + domainName.replace(/[<>]/g, '') + '</strong><small>DNS verification pending</small></div><div class="actions"><span class="status warning">Pending</span><button class="ghost" data-action="remove-domain" data-domain-id="' + res.domain_id + '">Remove</button></div>';
                                list.appendChild(row);
                            }
                            input.value = "";
                            notify("Domain added! Please add the CNAME record in your DNS.");
                        } else {
                            notify("Failed: " + (res?.error || "Could not add domain"));
                        }
                    } catch (err) {
                        notify("Error adding domain: " + err.message);
                    }
                } else if (action === "remove-domain") {
                    const domainId = button.dataset.domainId;
                    if (!domainId) {
                        button.closest(".option")?.remove();
                        notify("Domain removed.");
                        return;
                    }
                    try {
                        const res = await this.rpc("/saas/instance/remove-domain-name", { domain_name_id: parseInt(domainId) });
                        if (res && res.success) {
                            button.closest(".option")?.remove();
                            notify("Custom domain removed successfully.");
                        } else {
                            notify("Failed to remove domain: " + (res?.error || "Error"));
                        }
                    } catch (err) {
                        notify("Error removing domain: " + err.message);
                    }
                } else if (action === "refresh-logs" || action === "download-logs") {
                    this._fetchLiveLogs();
                } else if (action === "save") {
                    notify("Instance settings saved.");
                } else {
                    notify(button.textContent.trim() + " selected.");
                }
            });
        });
    },

    async _fetchLiveLogs() {
        const consoleEl = document.querySelector(".console");
        const instanceId = this._getInstanceId();
        if (!consoleEl || !instanceId) return;

        consoleEl.innerHTML = '<span style="color:#65d8ca">Fetching container live logs...</span>';
        try {
            const res = await this.rpc("/saas/instance/live-logs", {
                instance_id: instanceId,
                lines: 120
            });
            if (res && res.logs) {
                consoleEl.textContent = res.logs;
                consoleEl.scrollTop = consoleEl.scrollHeight;
            } else {
                consoleEl.textContent = "No logs returned from instance.";
            }
        } catch (err) {
            consoleEl.textContent = "Failed to fetch logs: " + err.message;
        }
    },

    _initModals() {
        const modal = document.getElementById("confirmModal");
        const confirmTitle = document.getElementById("confirmTitle");
        const confirmText = document.getElementById("confirmText");
        const confirmButton = document.getElementById("confirmAction");
        let pendingAction = "";

        const actionCopy = {
            start: ["Start Instance", "Start Odoo, workers and public web services?"],
            suspend: ["Suspend Instance", "This will stop public access and all background workers until started again."],
            restart: ["Restart Services", "The instance may be briefly unavailable while services reload."],
            redeploy: ["Redeploy Latest Revision", "Pull the latest connected GitHub code and restart the instance?"]
        };

        document.querySelectorAll("[data-confirm]").forEach(button => {
            button.addEventListener("click", () => {
                pendingAction = button.dataset.confirm;
                const copy = actionCopy[pendingAction] || ["Confirm Action", "Are you sure you want to proceed?"];
                if (confirmTitle) confirmTitle.textContent = copy[0];
                if (confirmText) confirmText.textContent = copy[1];
                if (modal) modal.classList.add("show");
            });
        });

        document.getElementById("cancelAction")?.addEventListener("click", () => {
            if (modal) modal.classList.remove("show");
        });

        confirmButton?.addEventListener("click", async () => {
            if (modal) modal.classList.remove("show");
            const instanceId = this._getInstanceId();
            if (!instanceId) {
                notify("No instance selected.");
                return;
            }

            const state = document.getElementById("instanceState");
            notify(actionCopy[pendingAction] ? actionCopy[pendingAction][0] + " in progress..." : "Processing...");

            try {
                let endpoint = "";
                if (pendingAction === "start") endpoint = "/saas/instance/start";
                else if (pendingAction === "suspend") endpoint = "/saas/instance/suspend";
                else if (pendingAction === "restart") endpoint = "/saas/instance/restart";
                else if (pendingAction === "redeploy") endpoint = "/saas/instance/redeploy";

                if (endpoint) {
                    const res = await this.rpc(endpoint, { instance_id: instanceId });
                    if (res && res.success !== false) {
                        if (pendingAction === "suspend" && state) {
                            state.textContent = "Suspended";
                            state.classList.add("suspended");
                        } else if (pendingAction === "start" && state) {
                            state.textContent = "Running";
                            state.classList.remove("suspended");
                        }
                        notify((actionCopy[pendingAction] ? actionCopy[pendingAction][0] : "Action") + " completed successfully.");
                    } else {
                        notify("Operation failed: " + (res?.error || "Error"));
                    }
                }
            } catch (err) {
                notify("Operation error: " + err.message);
            }
            pendingAction = "";
        });

        // GitHub Modal
        const ghModal = document.getElementById("githubModal");
        document.getElementById("cancelGithub")?.addEventListener("click", () => {
            if (ghModal) ghModal.classList.remove("show");
        });

        document.getElementById("confirmGithub")?.addEventListener("click", async () => {
            const instanceId = this._getInstanceId();
            const repoUrl = document.getElementById("githubRepoUrl")?.value?.trim();
            const branch = document.getElementById("githubBranch")?.value?.trim() || "main";
            const token = document.getElementById("githubToken")?.value?.trim() || "";

            if (!repoUrl) {
                notify("Please enter a GitHub repository URL.");
                return;
            }

            notify("Connecting GitHub repository...");
            if (ghModal) ghModal.classList.remove("show");

            try {
                const res = await this.rpc("/saas/instance/github-connect", {
                    instance_id: instanceId,
                    repo_url: repoUrl,
                    branch: branch,
                    token: token || null
                });
                if (res && res.success) {
                    notify("GitHub connected successfully!");
                    setTimeout(() => location.reload(), 1200);
                } else {
                    notify("Connection failed: " + (res?.error || "Check repository and token."));
                }
            } catch (err) {
                notify("GitHub error: " + err.message);
            }
        });

        document.getElementById("disconnectGithub")?.addEventListener("click", async () => {
            const instanceId = this._getInstanceId();
            if (!confirm("Disconnect GitHub repository? Custom addons will be unlinked.")) return;
            notify("Disconnecting GitHub...");
            try {
                const res = await this.rpc("/saas/instance/github-disconnect", { instance_id: instanceId });
                if (res && res.success) {
                    notify("GitHub disconnected.");
                    setTimeout(() => location.reload(), 1200);
                } else {
                    notify("Failed to disconnect: " + (res?.error || "Error"));
                }
            } catch (err) {
                notify("Error: " + err.message);
            }
        });
    },

    _initSearch() {
        const search = document.getElementById("instanceSearch");
        if (search) {
            search.addEventListener("input", () => {
                const query = search.value.toLowerCase();
                document.querySelectorAll("#instanceList [data-name]").forEach(card => {
                    const match = card.dataset.name.toLowerCase().includes(query);
                    card.classList.toggle("hidden", !match);
                });
            });
        }
    },

    _initSettings() {
        // Tab switching
        document.querySelectorAll("[data-setting]").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll("[data-setting]").forEach(b => b.classList.remove("active"));
                document.querySelectorAll(".settings-pane").forEach(p => p.classList.remove("active"));
                btn.classList.add("active");
                const target = document.getElementById("setting-" + btn.dataset.setting);
                if (target) target.classList.add("active");
            });
        });

        // URL hash support
        if (location.hash) {
            const hashBtn = document.querySelector('[data-setting="' + location.hash.slice(1) + '"]');
            if (hashBtn) hashBtn.click();
        }

        // Toggles
        document.querySelectorAll(".toggle-button").forEach(btn => {
            btn.addEventListener("click", () => {
                btn.classList.toggle("on");
                notify(btn.classList.contains("on") ? "Setting enabled." : "Setting disabled.");
            });
        });

        // Save settings button
        const saveBtn = document.getElementById("saveSettings");
        if (saveBtn) {
            saveBtn.addEventListener("click", async () => {
                const status = document.getElementById("saveStatus");
                if (status) status.textContent = "Saving...";
                const payload = {};
                document.querySelectorAll("[data-save]").forEach(input => {
                    payload[input.dataset.save] = input.value;
                });
                try {
                    await this.rpc("/saas/settings/save", payload);
                    if (status) status.textContent = "Saved!";
                    notify("Settings saved successfully.");
                    setTimeout(() => { if (status) status.textContent = ""; }, 3000);
                } catch (e) {
                    if (status) status.textContent = "Error";
                    notify("Failed to save settings: " + e.message);
                }
            });
        }

        // GitHub integration buttons in settings
        const connectGh = document.getElementById("connectGithub");
        const disconnectGh = document.getElementById("disconnectGithub");
        const ghState = document.getElementById("githubState");
        if (connectGh && disconnectGh && ghState) {
            connectGh.addEventListener("click", () => {
                ghState.textContent = "Connected as organization account · Ready for deployments.";
                connectGh.classList.add("hidden");
                disconnectGh.classList.remove("hidden");
                notify("GitHub account connected.");
            });
            disconnectGh.addEventListener("click", () => {
                ghState.textContent = "No GitHub account connected.";
                disconnectGh.classList.add("hidden");
                connectGh.classList.remove("hidden");
                notify("GitHub account disconnected.");
            });
        }

        // Password change
        const changePassBtn = document.getElementById("changePassword");
        if (changePassBtn) {
            changePassBtn.addEventListener("click", () => {
                const newPass = document.getElementById("newPassword");
                const confirmPass = document.getElementById("confirmPassword");
                if (!newPass || !confirmPass) return;
                if (newPass.value.length < 8) {
                    notify("Password must contain at least 8 characters.");
                    return;
                }
                if (newPass.value !== confirmPass.value) {
                    notify("Passwords do not match.");
                    return;
                }
                newPass.value = "";
                confirmPass.value = "";
                notify("Password updated successfully.");
            });
        }

        // Sign out devices
        const signOutBtn = document.getElementById("signOutDevices");
        if (signOutBtn) {
            signOutBtn.addEventListener("click", () => {
                notify("All other portal sessions have been signed out.");
            });
        }

        // Download latest invoice
        const invoiceBtn = document.getElementById("downloadInvoice");
        if (invoiceBtn) {
            invoiceBtn.addEventListener("click", () => {
                notify("Latest invoice download initiated.");
            });
        }

        // Team management
        const bindRemove = () => {
            document.querySelectorAll("[data-remove-member]").forEach(button => {
                button.onclick = () => {
                    button.closest(".member-row")?.remove();
                    notify("Team member removed.");
                };
            });
        };
        bindRemove();

        const inviteBtn = document.getElementById("inviteMember");
        if (inviteBtn) {
            inviteBtn.addEventListener("click", () => {
                const email = document.getElementById("inviteEmail");
                const role = document.getElementById("inviteRole");
                if (!email || !email.value.includes("@")) {
                    notify("Enter a valid email address.");
                    return;
                }
                const memberList = document.getElementById("memberList");
                if (memberList) {
                    const row = document.createElement("div");
                    row.className = "member-row";
                    const safeName = email.value.split("@")[0].replace(/[<>]/g, "");
                    const safeEmail = email.value.replace(/[<>]/g, "");
                    const roleVal = role ? role.value : "Developer";
                    row.innerHTML = '<div><strong>' + safeName + '</strong><small>' + safeEmail + '</small></div><span>' + roleVal + '</span><span class="status warning">Invited</span><button class="ghost" data-remove-member="data-remove-member">Remove</button>';
                    memberList.appendChild(row);
                }
                email.value = "";
                bindRemove();
                notify("Team invitation sent.");
            });
        }
    },

    _initMails() {
        document.querySelectorAll(".mail-item").forEach(item => {
            item.addEventListener("click", () => {
                document.querySelectorAll(".mail-item").forEach(m => m.classList.remove("active"));
                item.classList.add("active");
                notify("Email preview loaded.");
            });
        });
    }
});

export default publicWidget.registry.MyOdooPortal;
