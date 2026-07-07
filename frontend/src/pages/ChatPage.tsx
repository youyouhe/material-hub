import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, Send, Loader2, Trash2, Folder, Search, FileText, BarChart3, BookOpen, Brain, Copy, Plus, History } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { chatStreamWithLLM, type ChatMessage, type ToolUseEvent, listChatSessions, loadChatHistory, newChatSession, deleteChatSession } from '../services/api-v2';
import KnowledgeGraphPanel from '../components/KnowledgeGraphPanel';
import type { ChatSession } from '../services/api-v2';

interface ChatPageProps {
  folderId: number | null;
  folderName?: string;
  messages: ChatMessage[];
  onMessagesChange: (msgs: ChatMessage[]) => void;
  sessionId: number | null;
  onSessionChange: (sessionId: number | null) => void;
}

export default function ChatPage({ folderId, folderName, messages, onMessagesChange, sessionId, onSessionChange }: ChatPageProps) {
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [toolsUsed, setToolsUsed] = useState<ToolUseEvent[]>([]);
  const [graphEntity, setGraphEntity] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { loadSessions(); }, [sessionId]);

  const loadSessions = async () => {
    try {
      const data = await listChatSessions();
      setSessions(data.sessions);
    } catch { /* ignore */ }
  };

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
    setGraphEntity(null);

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
        // Detect kb_graph_explore calls and extract entity name for inline graph
        const graphTool = tools.find(t => t.tool === 'kb_graph_explore');
        if (graphTool?.args?.entity_name) {
          setGraphEntity(graphTool.args.entity_name as string);
        }
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

  const handleCopy = useCallback(async () => {
    const text = messages
      .map(m => `## ${m.role === 'user' ? '用户' : '助手'}\n${m.content}`)
      .join('\n\n');
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback for HTTP or older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      toast.success('已复制到剪贴板');
    } catch {
      // Last resort fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      toast.success('已复制');
    }
  }, [messages]);

  const handleNewSession = async () => {
    try {
      onMessagesChange([]);
      onSessionChange(null);
      const { session_id } = await newChatSession();
      onSessionChange(session_id);
      inputRef.current?.focus();
    } catch { toast.error('创建会话失败'); }
  };

  const handleSwitchSession = async (sid: number) => {
    try {
      const data = await loadChatHistory(sid);
      onSessionChange(sid);
      onMessagesChange(data.messages || []);
      setShowSessions(false);
    } catch { toast.error('加载会话失败'); }
  };

  const handleDeleteSession = async (sid: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('删除此对话？')) return;
    try {
      await deleteChatSession(sid);
      if (sessionId === sid) {
        onSessionChange(null);
        onMessagesChange([]);
      }
      await loadSessions();
    } catch { toast.error('删除失败'); }
  };

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
        <div className="flex items-center gap-2">
          {/* Session selector */}
          <div className="relative">
            <button onClick={() => setShowSessions(!showSessions)}
              className="text-cp-dim hover:text-cp-text text-sm flex items-center gap-1 transition-colors px-2 py-1 rounded cp-hover">
              <History className="w-3.5 h-3.5" /> 历史
            </button>
            {showSessions && (
              <div className="absolute right-0 top-8 w-64 cp-card rounded-lg p-2 z-50 shadow-lg space-y-0.5">
                {sessions.length === 0 ? (
                  <p className="text-cp-dim text-xs text-center py-2">暂无历史会话</p>
                ) : (
                  sessions.map(s => (
                    <div key={s.id}
                      onClick={() => handleSwitchSession(s.id)}
                      className={`flex items-center justify-between p-2 rounded cp-hover cursor-pointer text-sm ${
                        sessionId === s.id ? 'bg-cp-purple/10 border border-cp-purple/20' : ''
                      }`}>
                      <div className="flex-1 min-w-0">
                        <p className="text-cp-text truncate text-xs">{s.title || `对话 ${s.id}`}</p>
                        <p className="text-cp-dim text-xs">{s.message_count} 条 · {s.updated_at?.slice(0, 10)}</p>
                      </div>
                      <button onClick={(e) => handleDeleteSession(s.id, e)}
                        className="text-cp-dim hover:text-cp-rose ml-1 shrink-0">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          <button onClick={handleNewSession}
            className="text-cp-dim hover:text-cp-text text-sm flex items-center gap-1 transition-colors px-2 py-1 rounded cp-hover">
            <Plus className="w-3.5 h-3.5" /> 新建
          </button>

          {messages.length > 0 && (
            <>
              <button onClick={handleCopy}
                className="text-cp-dim hover:text-cp-text text-sm flex items-center gap-1 transition-colors px-2 py-1 rounded cp-hover">
                <Copy className="w-3.5 h-3.5" /> 复制
              </button>
              <button onClick={handleClear}
                className="text-cp-dim hover:text-cp-rose text-sm flex items-center gap-1 transition-colors px-2 py-1 rounded cp-hover">
                <Trash2 className="w-3.5 h-3.5" /> 清空
              </button>
            </>
          )}
        </div>
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

        {/* Inline knowledge graph (rendered when agent calls kb_graph_explore) */}
        {graphEntity && (
          <div className="flex justify-start mb-4">
            <div className="max-w-[80%] w-full">
              <KnowledgeGraphPanel
                entityName={graphEntity}
                compact
                onClose={() => setGraphEntity(null)}
              />
            </div>
          </div>
        )}
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
