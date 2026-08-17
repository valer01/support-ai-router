function dashboard() {
  return {
    me: null,
    claudeAvailable: false,
    teams: [],
    oncall: [],
    requests: [],
    auditLog: [],

    // chat state
    requester: "",
    conversationId: null,
    messages: [],
    draft: "",
    waiting: false,
    resolution: null,

    async init() {
      await this.loadMe();
      // The dashboard is already behind login (session-auth middleware
      // blocks everything else), so use the logged-in identity as the
      // requester automatically -- no separate "enter your name" gate
      // that a first-time message could accidentally get typed into.
      this.requester = (this.me && (this.me.email || this.me.username)) || "web-user";
      const greetName = this.requester.split("@")[0];
      this.messages = [
        { role: "assistant", content: `Hi ${greetName}! Tell me what's going on and I'll route it to the right team.` },
      ];
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

    startNewChat() {
      this.conversationId = null;
      this.resolution = null;
      this.draft = "";
      this.messages = [
        { role: "assistant", content: "New request — what's going on?" },
      ];
    },

    scrollChat() {
      const el = this.$refs.chatlog;
      if (el) el.scrollTop = el.scrollHeight;
    },

    async send() {
      const text = this.draft.trim();
      if (!text || this.waiting) return;
      this.messages.push({ role: "user", content: text });
      this.draft = "";
      this.waiting = true;
      this.$nextTick(() => this.scrollChat());

      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            conversation_id: this.conversationId,
            requester: this.requester,
            message: text,
          }),
        });
        const data = await r.json();
        this.conversationId = data.conversation_id;
        this.messages.push({ role: "assistant", content: data.message });

        if (data.status === "auto_routed" || data.status === "pending_review") {
          this.resolution = data;
          this.claudeAvailable = !data.message.includes("having trouble reaching");
          await Promise.all([this.loadRequests(), this.loadAudit()]);
        }
      } catch (e) {
        this.messages.push({
          role: "assistant",
          content: "Sorry, something went wrong reaching the server. Please try again.",
        });
      } finally {
        this.waiting = false;
        this.$nextTick(() => this.scrollChat());
      }
    },
  };
}
