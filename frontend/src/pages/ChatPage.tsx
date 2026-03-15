import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, Send, Loader2, Trash2, Folder, Search, FileText, BarChart3, BookOpen, Brain } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { chatStreamWithLLM, type ChatMessage, type ToolUseEvent } from '../services/api-v2';

interface ChatPageProps {
  folderId: number | null;
  folderName?: string;
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
}

export default function ChatPage({ folderId, folderName, messages, onMessagesChange }: ChatPageProps) {
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [toolsUsed, setToolsUsed] = useState<ToolUseEvent[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  // Use ref to track latest messages for streaming callbacks
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    const newMessages = [...messagesRef.current, userMsg];
    onMessagesChange(newMessages);
    setInput('');
    setStreaming(true);
    setToolsUsed([]);

    // Add empty assistant message for streaming
    onMessagesChange([...newMessages, { role: 'assistant', content: '' }]);

    let fullReply = '';

    await chatStreamWithLLM(
      newMessages,
      folderId,
      (chunk) => {
        fullReply += chunk;
        onMessagesChange([...newMessages, { role: 'assistant', content: fullReply }]);
      },
      () => {
        setStreaming(false);
        setToolsUsed([]);
        if (!fullReply) {
          onMessagesChange(newMessages);
          toast.error('未收到回复');
        }
      },
      (err) => {
        setStreaming(false);
        setToolsUsed([]);
        onMessagesChange(newMessages);
        toast.error(`对话失败: ${err}`);
      },
      (tools) => {
        setToolsUsed(tools);
      },
    );
  }, [input, streaming, folderId, onMessagesChange]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleClear = useCallback(() => {
    onMessagesChange([]);
    inputRef.current?.focus();
  }, [onMessagesChange]);

  const _toolIcon = (toolName: string) => {
    const cls = "w-3.5 h-3.5 text-cp-cyan";
    switch (toolName) {
      case 'search_documents': return <Search className={cls} />;
      case 'get_document_detail': return <FileText className={cls} />;
      case 'read_document_content': return <BookOpen className={cls} />;
      case 'list_documents': return <FileText className={cls} />;
      case 'get_statistics': return <BarChart3 className={cls} />;
      default: return <Brain className={cls} />;
    }
  };

  const _toolLabel = (t: ToolUseEvent) => {
    switch (t.tool) {
      case 'search_documents': return `searching "${(t.args as Record<string, string>).query || ''}"...`;
      case 'get_document_detail': return `reading document #${(t.args as Record<string, number>).doc_id || ''}...`;
      case 'read_document_content': return `reading document content #${(t.args as Record<string, number>).doc_id || ''}...`;
      case 'list_documents': return 'listing documents...';
      case 'get_statistics': return 'calculating statistics...';
      default: return t.label || t.tool;
    }
  };

  const SUGGESTIONS = [
    '这个文件夹下有哪些文档？',
    '帮我统计各类型文档数量',
    '有哪些即将到期的证书？',
    '总结一下公司资质情况',
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-cp-cyan" />
          智能助手
          {folderName && (
            <span className="text-sm font-exo font-normal text-cp-muted flex items-center gap-1">
              <Folder className="w-3.5 h-3.5" />
              {folderName}
            </span>
          )}
        </h2>
        {messages.length > 0 && (
          <button
            onClick={handleClear}
            className="text-cp-dim hover:text-cp-text text-sm flex items-center gap-1 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空对话
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-4 pb-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-cp-dim">
            <MessageSquare className="w-16 h-16 mb-4 opacity-30" />
            <p className="text-lg mb-1">有什么可以帮你？</p>
            <p className="text-sm mb-6">基于{folderName ? `"${folderName}"文件夹` : '全部文档'}为你提供智能服务</p>
            <div className="grid grid-cols-2 gap-2 max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => { setInput(s); inputRef.current?.focus(); }}
                  className="text-left text-sm px-3 py-2 rounded-lg border border-cp-border hover:border-cp-purple/50 hover:bg-cp-purple/5 text-cp-muted transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div
                className={clsx(
                  'max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-cp-purple/20 text-cp-text border border-cp-purple/20'
                    : 'cp-card text-cp-text'
                )}
              >
                {msg.role === 'assistant' && !msg.content && streaming ? (
                  <div className="space-y-2">
                    {toolsUsed.length > 0 ? (
                      <div className="space-y-1">
                        {toolsUsed.map((t, ti) => (
                          <span key={ti} className="flex items-center gap-1.5 text-cp-dim text-xs">
                            {_toolIcon(t.tool)}
                            {_toolLabel(t)}
                          </span>
                        ))}
                        <span className="flex items-center gap-2 text-cp-dim text-sm mt-1">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Generating response...
                        </span>
                      </div>
                    ) : (
                      <span className="flex items-center gap-2 text-cp-dim">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        thinking...
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 pt-2 border-t border-cp-border">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题... (Enter 发送, Shift+Enter 换行)"
            rows={1}
            className="cp-input flex-1 rounded-lg px-4 py-2.5 text-sm resize-none max-h-32 overflow-y-auto"
            style={{ minHeight: '42px' }}
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="cp-btn-primary px-4 py-2.5 rounded-lg disabled:opacity-30 shrink-0"
          >
            {streaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
