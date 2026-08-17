function dashboard() {
  return {
    me: null,
    claudeAvailable: false,
    teams: [],
    oncall: [],
    requests: [],
    auditLog: [],
    newRequest: { requester: "", text: "" },
    submitting: false,
    lastResult: null,

    async init() {
      await this.loadMe();
      await Promise.all([
        this.loadTeams(),
        this.loadOncall(),
        this.loadRequests(),
        this.loadAudit(),
      ]);
    },

    async loadMe() {
      const r = await fetch("/auth/me");
      const data = await r.json();
      this.me = data.user;
    },

    async loadTeams() {
      const r = await fetch("/api/teams");
      const data = await r.json();
      this.teams = data.teams || [];
    },

    async loadOncall() {
      const r = await fetch("/api/oncall");
      const data = await r.json();
      this.oncall = data.oncall || [];
    },

    async loadRequests() {
      const r = await fetch("/api/requests");
      const data = await r.json();
      this.requests = data.requests || [];
    },

    async loadAudit() {
      const r = await fetch("/api/audit");
      const data = await r.json();
      this.auditLog = data.entries || [];
    },

    async submitRequest() {
      if (!this.newRequest.text || !this.newRequest.requester) return;
      this.submitting = true;
      try {
        const r = await fetch("/api/requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requester: this.newRequest.requester,
            text: this.newRequest.text,
            source: "web",
          }),
        });
        const data = await r.json();
        this.lastResult = data;
        this.claudeAvailable = data.reasoning && !data.reasoning.includes("[LLM unavailable");
        this.newRequest.text = "";
        await Promise.all([this.loadRequests(), this.loadAudit()]);
      } finally {
        this.submitting = false;
      }
    },
  };
}
