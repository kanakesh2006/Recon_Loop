import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "../api";

interface ChatMessage {
  role: "user" | "copilot";
  content: string;
}

const WELCOME: ChatMessage = {
  role: "copilot",
  content:
    'Hi! I\'m the ReconLoop settlement copilot. Ask me about any order, exception, fee math, or reconciliation policy — e.g. "Why is order order_ad3wrdhw9re2q6 in the exception queue?"',
};

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-2">
      <span className="typing-dot h-2 w-2 rounded-full bg-indigo-300" />
      <span className="typing-dot h-2 w-2 rounded-full bg-indigo-300" />
      <span className="typing-dot h-2 w-2 rounded-full bg-indigo-300" />
      <span className="ml-2 text-xs text-slate-400">copilot is thinking…</span>
    </div>
  );
}

export default function CopilotChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, pending]);

  const send = async () => {
    const question = input.trim();
    if (!question || pending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setPending(true);
    try {
      const reply = await sendChatMessage(question);
      setMessages((prev) => [...prev, { role: "copilot", content: reply }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        {
          role: "copilot",
          content: `Sorry — the copilot is unavailable right now. (${message})`,
        },
      ]);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl">
      <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 to-fuchsia-500 text-sm font-black text-white">
          AI
        </div>
        <div>
          <p className="text-sm font-bold text-slate-100">Settlement Copilot</p>
          <p className="text-[11px] text-slate-400">
            grounded in your transactions, policies & audit trail
          </p>
        </div>
        <span
          className={`ml-auto h-2 w-2 rounded-full ${pending ? "bg-amber-300" : "bg-emerald-400"}`}
          title={pending ? "thinking" : "ready"}
        />
      </div>

      <div
        ref={scrollRef}
        className="chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4"
      >
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                message.role === "user"
                  ? "rounded-br-md bg-gradient-to-br from-indigo-500 to-fuchsia-600 text-white"
                  : "rounded-bl-md border border-white/10 bg-slate-800/70 text-slate-200"
              }`}
            >
              {message.content}
            </div>
          </div>
        ))}
        {pending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md border border-white/10 bg-slate-800/70">
              <TypingIndicator />
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-white/10 p-3">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about settlements, fees, exceptions…"
            disabled={pending}
            className="min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-900/60 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-400/60 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={pending || !input.trim()}
            className="rounded-xl bg-gradient-to-r from-indigo-500 to-fuchsia-600 px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
