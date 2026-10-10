import { useState } from "react";
import { Mic, Paperclip, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AiChatOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  role: string;
}

export function AiChatOverlay({ isOpen, onClose, role }: AiChatOverlayProps) {
  const [inputValue, setInputValue] = useState("");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="relative flex h-[90vh] w-[90vw] max-w-4xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-muted/50 p-4">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-full bg-primary/20 text-primary">
              <span className="text-xs font-bold">AI</span>
            </div>
            <div>
              <h2 className="text-sm font-semibold">Resident AI Assistant</h2>
              <p className="text-xs text-muted-foreground">Automating your workflow</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X size={18} />
          </Button>
        </div>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex max-w-[80%] gap-3">
            <div className="mt-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
              AI
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-muted p-4 text-sm leading-relaxed text-foreground">
              <p>
                Hello! I noticed you're logged in as a <strong>{role}</strong>. 
                <br /><br />
                What have you been up to recently, and what do you need to get done today? I can update your milestones, log blockers, and organize your syllabus progress automatically.
              </p>
            </div>
          </div>
        </div>

        {/* Input Area */}
        <div className="border-t border-border bg-background p-4">
          <div className="flex items-end gap-2 rounded-xl border border-input bg-background p-2 focus-within:ring-1 focus-within:ring-ring">
            <Button variant="ghost" size="icon" className="shrink-0 text-muted-foreground hover:text-foreground">
              <Paperclip size={18} />
              <span className="sr-only">Attach file</span>
            </Button>
            
            <textarea
              className="min-h-[40px] w-full resize-none bg-transparent py-2 text-sm placeholder:text-muted-foreground focus:outline-none"
              placeholder="Type your update here, or use voice..."
              rows={1}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
            />
            
            <div className="flex items-center gap-1 shrink-0">
              <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-foreground">
                <Mic size={18} />
                <span className="sr-only">Voice input</span>
              </Button>
              <Button size="icon" className="rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
                <Send size={16} />
                <span className="sr-only">Send message</span>
              </Button>
            </div>
          </div>
          <p className="mt-2 text-center text-[10px] text-muted-foreground">
            The AI can process text, voice notes, and document uploads to automate your dashboard tasks.
          </p>
        </div>
      </div>
    </div>
  );
}
