import { useState } from "react";
import { 
  Bot, 
  CheckCircle2, 
  FileText, 
  Mic, 
  Paperclip, 
  Plus, 
  Send, 
  Sparkles, 
  UploadCloud, 
  UserPlus, 
  X 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Founder } from "./data";

interface Message {
  id: string;
  sender: "ai" | "user";
  text: string;
  files?: string[];
  actionPill?: boolean;
}

interface AiChatOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  role: string;
  onAddFounder?: (founder: Founder) => void;
}

export function AiChatOverlay({ isOpen, onClose, role, onAddFounder }: AiChatOverlayProps) {
  const [inputValue, setInputValue] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [dispatchedSlack, setDispatchedSlack] = useState<Record<string, { leads?: boolean; gwenBen?: boolean }>>({});
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "m-1",
      sender: "ai",
      text: `Hello! I am MVP_buddy, your resident Venture Studio AI. I orchestrate founder operations and enforce the pre-build demand validation protocol.\n\nWould you like to onboard a new founder to Cohort SG#01, log a sprint check-in, audit active blockers, or dispatch a message to Gwen & Ben on Slack?`,
    },
  ]);

  if (!isOpen) return null;

  const handleDispatchToSlack = async (
    msgId: string, 
    text: string, 
    target: "leads" | "gwenBen" = "leads"
  ) => {
    setDispatchedSlack((prev) => ({
      ...prev,
      [msgId]: {
        ...prev[msgId],
        [target]: true,
      },
    }));
    
    const targetLabel = target === "gwenBen" ? "Gwen & Ben (#cybrdeck-leads)" : "#mamba-leads";

    // Check if user set a live webhook URL in localStorage
    const webhookUrl = typeof window !== "undefined" ? localStorage.getItem("mamba_slack_webhook") : null;
    if (webhookUrl) {
      try {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: `[MVP_buddy Dashboard Dispatch to ${targetLabel}]\n${text}`,
          }),
        });
      } catch (err) {
        console.warn("Slack webhook transmission error:", err);
      }
    }
  };

  const handleQuickOnboard = (preset: "maya" | "liam") => {
    const founderData: Founder = preset === "maya" 
      ? {
          id: `founder-maya-${Date.now()}`,
          name: "Maya Torres",
          startup: "PayFlow · Cross-Border B2B Clearing",
          stream: "Tech",
          lead: "Gwen & Ben (Cybrdeck)",
          status: "In progress",
          digest: "Validated merchant clearing with 5 SMEs in Singapore. Wire transfers are currently manual; building spreadsheet-driven mock ledger to prove demand before API automation.",
          time: "Just now",
          progress: 75,
          audience: "Regional B2B import/export merchants",
          stack: ["React", "FastAPI", "Stripe Connect", "Supabase"],
          blocker: "Waiting on MAS regulatory guideline clarity for cross-border FX escrows.",
          profile: "Maya is an ex-Stripe product engineer building automated cross-border treasury settlements. Focusing on manual concierge MVP execution.",
          transcript: "Interviewed 5 importers today. All 5 are willing to pay a 15 bps spread if settlement settles in under 2 hours. Setting up the manual concierge batch processing.",
          note: "Cybrdeck Protocol: Enforce manual batch ledger before provisioning AWS payment microservices.",
        }
      : {
          id: `founder-liam-${Date.now()}`,
          name: "Liam Chen",
          startup: "RoboPick · Autonomous Warehouse Telemetry",
          stream: "GTM",
          lead: "James Sun (Mamba)",
          status: "Blocked",
          digest: "Shadowed 2 logistics operators in Jurong. Identified barcode scanner latency as the primary friction point. Currently blocked on site survey safety approvals.",
          time: "Just now",
          progress: 50,
          audience: "Tier-2 3PL fulfillment hubs in SEA",
          stack: ["Mobile Web App", "WebSockets", "Go"],
          blocker: "Warehouse safety manager delayed the LiDAR telemetry sensor pilot by 1 week.",
          profile: "Liam is validating camera-based stock tracking for logistics centers without requiring million-dollar robotics overhauls.",
          transcript: "The warehouse walkthrough went well but safety compliance pushed back our camera install to next Tuesday. Need advice from Mamba on remote validation techniques.",
          note: "Mamba GTM: Guide Liam on running manual time-motion surveys while waiting on hardware clearances.",
        };

    // User message
    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: `Please onboard a new founder: ${founderData.name} (${founderData.startup}).`,
      files: [
        "Problem_Thesis_v1.pdf",
        "3_Customer_Discovery_Transcripts.txt",
        "Technical_Architecture_Overview.png"
      ]
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);

    setTimeout(() => {
      setIsProcessing(false);
      const aiReply: Message = {
        id: `ai-${Date.now()}`,
        sender: "ai",
        text: `✅ **Onboarding Protocol Complete for ${founderData.name}!**\n\n` +
          `• **Intake Audit**: Ingested *Problem Thesis*, *3 Customer Transcripts*, and *Architecture Diagram*.\n` +
          `• **Pre-Build Validation Check**: Manual customer demand baseline verified (${founderData.stream === "Tech" ? "Concierge Ledger" : "Manual Surveys"}).\n` +
          `• **Baseline Velocity**: Set to **${founderData.progress}%**.\n` +
          `• **Active Status**: ${founderData.status === "Blocked" ? "🔴 Blocked" : "🟢 In Progress"}.\n\n` +
          `I've minted ${founderData.name}'s **Pokemon Card** and added them to the live Cohort SG#01 roster! 🚀`,
      };
      setMessages((prev) => [...prev, aiReply]);
      if (onAddFounder) {
        onAddFounder(founderData);
      }
    }, 1200);
  };

  const handleRunAction = (action: "triage" | "gate" | "reality" | "briefing" | "coordinator") => {
    let userPrompt = "";
    let aiResponse = "";

    if (action === "coordinator") {
      userPrompt = "Coordinator Hand-off: Review Jordan Lee milestone and ping engineering mentor";
      aiResponse = `Sprint 1 Milestone Hand-Off (Ready for Mentor Action):\n\n` +
        `• Venture: Jordan Lee (Vitals.co)\n` +
        `• Status: Pre-Build Demand Validation Complete (3 clinic interviews logged; doctor willingness-to-pay confirmed manually before allocating backend engineering).\n` +
        `• Active Bottleneck: PDF biomarker OCR parser drops hormone fields across clinical lab variations.\n\n` +
        `AI Recommendation:\n` +
        `Dispatch an immediate Slack notification to Gwen Lim (@gwen.lim) to review the parsing regex logic and clear Jordan's Sprint 1 milestone.`;
    } else if (action === "triage") {
      userPrompt = "Run Cohort Triage";
      aiResponse = `Cohort Triage (Active Telemetry):\n\n` +
        `• Jordan Lee (Vitals.co): Stalled on OCR biomarker field extraction for 48 hours. Risk: Data schema handoff delay for backend engineering.\n` +
        `  Suggested Intervention: Pair with Ben Lim for a 20-minute regex parsing review.\n\n` +
        `• Alex Vance (Nexus Logistics): Discovery completed; waiting on copy feedback before LinkedIn ad rollout.\n` +
        `  Suggested Intervention: Clear headline copy with James Sun today.\n\n` +
        `• Summary: 1 critical path blocker flagged. Cohort momentum remains at 88%.`;
    } else if (action === "gate") {
      userPrompt = "Run Milestone Gate Check";
      aiResponse = `Friday Milestone Gate Readiness:\n\n` +
        `Upcoming Gate: 1-Page Venture Thesis & Top 10 Ranked Assumptions\n\n` +
        `• Alex Vance: 80% ready. Problem thesis drafted and verified against 4 warehouse interviews. High probability of passing Friday evaluation.\n` +
        `• Jordan Lee: 60% ready. Core clinical thesis verified, but deliverable delayed due to OCR data pipeline blocker. Conditional pass risk.\n\n` +
        `• Advisory Recommendation: Dedicate today's 45-minute sync to Jordan's data pipeline so both ventures clear Friday gate.`;
    } else if (action === "reality") {
      userPrompt = "Run Pre-Build Reality Check";
      aiResponse = `Pre-Build Demand Validation Status:\n\n` +
        `Enforcing customer proof before custom engineering allocation:\n\n` +
        `• Alex Vance (Nexus Logistics): COMPLIANT. Validated customer demand manually with 4 warehouse managers using spreadsheet matching before building automated routing.\n` +
        `• Jordan Lee (Vitals.co): COMPLIANT. Manually running OCR parsing scripts with doctors to verify willingness-to-pay before requesting automated cloud infrastructure.\n\n` +
        `• Audit Result: 100% of cohort ventures are adhering to pre-build demand validation. Zero premature engineering hours burned.`;
    } else if (action === "briefing") {
      userPrompt = "Generate 60-Second Lead Briefing";
      aiResponse = `60-Second Lead Briefing:\n` +
        `-----------------------------------------\n` +
        `Mamba SG#01 Pulse (Oct 13):\n` +
        `• Active Ventures: 2 (Nexus Logistics, Vitals.co)\n` +
        `• Cohort Momentum: 88% on track\n` +
        `• Priority Fire: Jordan Lee OCR parser bottleneck (>48h)\n` +
        `• Today's Action: Ben Lim unblocking Jordan; James Sun copy review for Alex.\n` +
        `-----------------------------------------\n` +
        `(Ready to copy into leadership Slack)`;
    }

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: userPrompt,
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsProcessing(true);

    setTimeout(() => {
      setIsProcessing(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: "ai",
          text: aiResponse,
        },
      ]);
    }, 700);
  };

  const handleSend = () => {
    if (!inputValue.trim()) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: inputValue,
    };
    setMessages((prev) => [...prev, userMsg]);
    const inputCopy = inputValue;
    setInputValue("");
    setIsProcessing(true);

    setTimeout(() => {
      setIsProcessing(false);
      let reply = "";
      const lower = inputCopy.toLowerCase();
      if (lower.includes("founder") || lower.includes("onboard") || lower.includes("add")) {
        reply = `📋 **Onboarding Protocol Triggered!**\n\nTo onboard a founder and generate their live card, I require the **3 Standard Intake Documents**:\n\n1. 📄 **Problem & Founder Thesis** (Sprint 1 Milestone)\n2. 🎙️ **At least 3 Customer Discovery Transcripts** (Validating demand before custom engineering)\n3. 🛠️ **Current Tech Stack & Slack User ID** (For autonomous telemetry)\n\nYou can click the quick demo buttons below to test-ingest pre-validated founder files!`;
      } else if (lower.includes("gwen") || lower.includes("ben")) {
        reply = `📣 **Slack Mentor Dispatch Prepared!**\n\n` +
          `• **Recipients**: Gwen Lim (<@U_GWEN>) & Ben Lim (<@U_BEN>)\n` +
          `• **Channel**: #cybrdeck-leads / Mentor Direct Channel\n` +
          `• **Draft Content**:\n` +
          `  "Hey Gwen & Ben, MVP_buddy engineering alert from Mamba SG#01:\n` +
          `  Jordan Lee (Vitals.co) has been blocked on OCR biomarker regex parsing for >48h. Manual doctor willingness-to-pay is already verified under pre-build validation protocol. Requesting a 15-minute pairing unblocker with Cybrdeck engineering today."\n\n` +
          `Click below to notify Gwen & Ben directly on Slack.`;
      } else if (lower.includes("slack") || lower.includes("poke") || lower.includes("notify") || lower.includes("message")) {
        const isJordan = lower.includes("jordan");
        const isAlex = lower.includes("alex");
        const recipient = isJordan ? "Jordan Lee (Vitals.co)" : isAlex ? "Alex Vance (Nexus Logistics)" : "Mamba Cohort Leads";
        const channel = isJordan || isAlex ? `#mamba-sg01-checkins / DM` : `#mamba-leads`;
        
        reply = `📣 **Slack Dispatch Prepared!**\n\n` +
          `• **Target Channel / Recipient**: ${channel} (${recipient})\n` +
          `• **Draft Content**:\n` +
          `  "Hey ${isJordan ? "Jordan" : isAlex ? "Alex" : "team"}, MVP_buddy check-in: ${
            isJordan 
              ? "Noticed the OCR biomarker parsing script has been blocked for 48h. Gwen and Ben have a regex solution ready—let's do a 15-min pairing sync." 
              : isAlex 
              ? "Discovery validation phase complete. Ready for copy sign-off with James Sun before live landing page deployment." 
              : "Active cohort check-in logged from studio dashboard."
          }"\n\n` +
          `Click below to dispatch this message directly to Slack.`;
      } else {
        reply = `Understood! I've noted this in the ambient ledger. If this impacts sprint milestones or introduces a blocker, I will update the cohort velocity and alert Gwen & Ben.`;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          sender: "ai",
          text: reply,
        },
      ]);
    }, 900);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-muted/40 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Bot size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-foreground">MVP_buddy · Autonomous Studio Concierge</h2>
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
                  Live Telemetry
                </span>
              </div>
              <p className="text-xs text-muted-foreground">Pre-Build Demand Validation & Cohort Ingestion</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="rounded-full">
            <X size={18} />
          </Button>
        </div>

        {/* Quick Action Chips (Clean Typography, No Icons) */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-muted/20 px-6 py-2.5">
          <span className="text-[11px] font-semibold text-muted-foreground mr-1">
            Quick Actions:
          </span>
          <button
            onClick={() => handleRunAction("coordinator")}
            className="rounded-md border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/20 transition-colors cursor-pointer shadow-2xs"
          >
            Coordinator Hand-off
          </button>
          <button
            onClick={() => handleRunAction("triage")}
            className="rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer shadow-2xs"
          >
            Cohort Triage
          </button>
          <button
            onClick={() => handleRunAction("gate")}
            className="rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer shadow-2xs"
          >
            Milestone Gate Check
          </button>
          <button
            onClick={() => handleRunAction("reality")}
            className="rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer shadow-2xs"
          >
            Pre-Build Reality Check
          </button>
          <button
            onClick={() => handleRunAction("briefing")}
            className="rounded-md border border-border bg-card px-3 py-1 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer shadow-2xs"
          >
            60-Second Lead Briefing
          </button>
        </div>

        {/* Chat Stream */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex gap-3 max-w-[85%] ${
                m.sender === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
              }`}
            >
              <div
                className={`flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                  m.sender === "user"
                    ? "bg-foreground text-background"
                    : "bg-primary text-primary-foreground shadow-xs"
                }`}
              >
                {m.sender === "user" ? "You" : "AI"}
              </div>

              <div
                className={`rounded-2xl p-4 text-xs leading-relaxed ${
                  m.sender === "user"
                    ? "bg-primary text-primary-foreground rounded-tr-xs"
                    : "bg-muted/80 text-foreground rounded-tl-xs border border-border/40"
                }`}
              >
                <div className="whitespace-pre-line">{m.text}</div>

                {m.files && m.files.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5 pt-2 border-t border-primary-foreground/20">
                    {m.files.map((f, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 rounded bg-black/15 px-2 py-0.5 text-[10px] font-mono"
                      >
                        <FileText size={10} />
                        {f}
                      </span>
                    ))}
                  </div>
                )}

                {/* Outbound Slack Dispatch Actions */}
                {m.sender === "ai" && m.id !== "m-1" && (
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/50 text-[11px]">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {dispatchedSlack[m.id]?.leads ? (
                        <span className="font-medium text-emerald-700 bg-emerald-500/15 px-2 py-0.5 rounded text-[10px]">
                          Dispatched to #mamba-leads
                        </span>
                      ) : (
                        <button
                          onClick={() => handleDispatchToSlack(m.id, m.text, "leads")}
                          className="rounded border border-border bg-card px-2 py-0.5 font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer text-[10px] shadow-2xs"
                        >
                          Post to #mamba-leads
                        </button>
                      )}

                      {dispatchedSlack[m.id]?.gwenBen ? (
                        <span className="font-medium text-emerald-700 bg-emerald-500/15 px-2 py-0.5 rounded text-[10px]">
                          Sent to Gwen & Ben (@gwen.lim, @ben.lim)
                        </span>
                      ) : (
                        <button
                          onClick={() => handleDispatchToSlack(m.id, m.text, "gwenBen")}
                          className="rounded border border-border bg-card px-2 py-0.5 font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-colors cursor-pointer text-[10px] shadow-2xs"
                        >
                          Notify Gwen & Ben
                        </button>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground font-medium">
                      Slack Integration
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isProcessing && (
            <div className="flex gap-3 items-center text-xs text-muted-foreground animate-pulse">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary">
                <Bot size={14} />
              </div>
              <span>MVP_buddy is auditing intake documents & validating protocol...</span>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="border-t border-border bg-card p-4">
          <div className="flex items-center gap-2 rounded-xl border border-input bg-background p-2 focus-within:ring-1 focus-within:ring-primary">
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0 text-muted-foreground hover:text-foreground rounded-lg"
              title="Attach documents"
              onClick={() => handleQuickOnboard("maya")}
            >
              <Paperclip size={18} />
            </Button>

            <input
              type="text"
              className="w-full bg-transparent px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
              placeholder="Ask to onboard a founder, upload transcripts, or log blockers..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />

            <Button
              size="icon"
              className="rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 cursor-pointer shrink-0"
              onClick={handleSend}
            >
              <Send size={15} />
            </Button>
          </div>
          <p className="mt-2 text-center text-[10px] text-muted-foreground">
            Enforces Cybrdeck pre-build demand validation before allocating custom engineering hours.
          </p>
        </div>
      </div>
    </div>
  );
}
