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
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "m-1",
      sender: "ai",
      text: `Hello! I am MVP_buddy, your resident Venture Studio AI. I orchestrate founder operations and enforce the Wizard-of-Oz protocol.\n\nWould you like to onboard a new founder to Cohort SG#01, log a sprint check-in, or audit active blockers?`,
    },
  ]);

  if (!isOpen) return null;

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
          `• **Wizard-of-Oz Check**: Manual demand baseline verified (${founderData.stream === "Tech" ? "Concierge Ledger" : "Manual Surveys"}).\n` +
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
      if (inputCopy.toLowerCase().includes("founder") || inputCopy.toLowerCase().includes("onboard") || inputCopy.toLowerCase().includes("add")) {
        reply = `📋 **Onboarding Protocol Triggered!**\n\nTo onboard a founder and generate their live card, I require the **3 Standard Intake Documents**:\n\n1. 📄 **Problem & Founder Thesis** (Sprint 1 Milestone)\n2. 🎙️ **At least 3 Customer Discovery Transcripts** (Validating demand under Wizard-of-Oz)\n3. 🛠️ **Current Tech Stack & Slack User ID** (For autonomous telemetry)\n\nYou can click the quick demo buttons below to test-ingest pre-validated founder files!`;
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
              <p className="text-xs text-muted-foreground">Wizard-of-Oz Protocol & Cohort SG#01 Ingestion</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="rounded-full">
            <X size={18} />
          </Button>
        </div>

        {/* Quick Action Bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-muted/20 px-6 py-2.5">
          <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
            <Sparkles size={12} className="text-primary" /> Quick Protocols:
          </span>
          <button
            onClick={() => handleQuickOnboard("maya")}
            className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20 cursor-pointer"
          >
            <UserPlus size={12} />
            + Onboard Maya Torres (PayFlow · Tech)
          </button>
          <button
            onClick={() => handleQuickOnboard("liam")}
            className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-500/20 cursor-pointer"
          >
            <UserPlus size={12} />
            + Onboard Liam Chen (RoboPick · GTM)
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
            Enforces Cybrdeck Wizard-of-Oz demand validation before writing custom backend code.
          </p>
        </div>
      </div>
    </div>
  );
}
