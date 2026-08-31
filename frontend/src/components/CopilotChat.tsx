import { useEffect, useRef, useState, useCallback } from "react";
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
      <span className="typing-dot h-2 w-2 rounded-full bg-brown-lighter" />
      <span className="typing-dot h-2 w-2 rounded-full bg-brown-lighter" />
      <span className="typing-dot h-2 w-2 rounded-full bg-brown-lighter" />
      <span className="ml-2 text-xs text-muted">copilot is thinking…</span>
    </div>
  );
}

export default function CopilotChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, pending]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = false;
        recognitionRef.current.interimResults = true;
        
        recognitionRef.current.onresult = (event: any) => {
          let currentTranscript = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            currentTranscript += event.results[i][0].transcript;
          }
          setInput(currentTranscript);
        };

        recognitionRef.current.onerror = (event: any) => {
          console.error("Speech recognition error", event.error);
          setIsListening(false);
        };

        recognitionRef.current.onend = () => {
          setIsListening(false);
        };
      }
    }
  }, []);

  const toggleListen = useCallback(() => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      if (recognitionRef.current) {
        setInput("");
        recognitionRef.current.start();
        setIsListening(true);
      } else {
        alert("Speech recognition is not supported in this browser.");
      }
    }
  }, [isListening]);

  const send = async () => {
    const question = input.trim();
    if (!question || pending) return;
    setInput("");
    if (isListening) toggleListen();
    
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
    <div className="flex h-full min-h-[500px] flex-col rounded-lg border border-brown/10 bg-white/60 shadow-sm backdrop-blur-xl">
      <div className="flex items-center gap-3 border-b border-brown/10 px-5 py-4 bg-brown/5 rounded-t-lg">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brown via-brown-light to-brown-lighter text-sm font-black text-cream">
          AI
        </div>
        <div>
          <p className="text-sm font-bold text-brown">Settlement Copilot</p>
          <p className="text-[11px] text-slate-600">
            grounded in your transactions, policies & audit trail
          </p>
        </div>
        <span
          className={`ml-auto h-2 w-2 rounded-full ${pending ? "bg-amber-400" : isListening ? "bg-red-500 animate-pulse" : "bg-emerald-500"}`}
          title={pending ? "thinking" : isListening ? "listening" : "ready"}
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
              className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                message.role === "user"
                  ? "rounded-br-sm bg-gradient-to-br from-brown via-brown-light to-brown-lighter text-cream shadow-sm"
                  : "rounded-bl-sm border border-brown/10 bg-white text-brown shadow-sm"
              }`}
            >
              {message.content}
            </div>
          </div>
        ))}
        {pending && (
          <div className="flex justify-start">
            <div className="rounded-lg rounded-bl-sm border border-brown/10 bg-white shadow-sm">
              <TypingIndicator />
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-brown/10 p-3 bg-brown/5 rounded-b-lg">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
          className="flex gap-2 items-center"
        >
          <button
            type="button"
            onClick={toggleListen}
            className={`flex-shrink-0 flex items-center justify-center h-10 w-10 rounded-lg transition-colors ${
              isListening ? "bg-red-500 text-white animate-pulse" : "bg-white border border-brown/20 text-brown hover:bg-brown/5"
            }`}
            title="Dictate with voice"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </button>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={isListening ? "Listening..." : "Ask about settlements, fees..."}
            disabled={pending}
            className="min-w-0 flex-1 rounded-lg border border-brown/20 bg-white px-3.5 py-2.5 text-sm text-text-dark placeholder-slate-400 outline-none transition focus:border-brown focus:ring-1 focus:ring-brown disabled:opacity-50 shadow-sm"
          />
          <button
            type="submit"
            disabled={pending || !input.trim()}
            className="rounded-lg bg-gradient-to-r from-brown to-brown-light px-4 py-2.5 text-sm font-bold text-cream transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 shadow-sm"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
