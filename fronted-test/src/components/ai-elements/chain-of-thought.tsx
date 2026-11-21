import * as Collapsible from '@radix-ui/react-collapsible';
import {
  AlertCircleIcon,
  BrainIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ClockIcon,
  DatabaseIcon,
  FileSearchIcon,
  GlobeIcon,
  Loader2Icon,
  MessageSquareTextIcon,
  WrenchIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';

export type StepStatus = 'active' | 'pending' | 'complete' | 'error';

export function ChainOfThought({
  open,
  defaultOpen = true,
  onOpenChange,
  children,
}: {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Collapsible.Root
      className="ai-cot"
      open={open}
      defaultOpen={defaultOpen}
      onOpenChange={onOpenChange}
    >
      {children}
    </Collapsible.Root>
  );
}

export function ChainOfThoughtHeader({
  isActive,
  children,
}: {
  isActive?: boolean;
  children: ReactNode;
}) {
  return (
    <Collapsible.Trigger className="ai-cot-header" type="button">
      <span className="ai-cot-header-left">
        {isActive ? (
          <Loader2Icon className="ai-cot-icon ai-cot-spin" size={16} aria-hidden="true" />
        ) : (
          <BrainIcon className="ai-cot-icon" size={16} aria-hidden="true" />
        )}
        <span>{children}</span>
      </span>
      <ChevronDownIcon className="ai-cot-chevron" size={16} aria-hidden="true" />
    </Collapsible.Trigger>
  );
}

export function ChainOfThoughtContent({ children }: { children: ReactNode }) {
  return (
    <Collapsible.Content className="ai-cot-content">
      <div className="ai-cot-steps">{children}</div>
    </Collapsible.Content>
  );
}

function KindIcon({ kind }: { kind: string }) {
  switch (kind) {
    case 'web_search':
      return <GlobeIcon size={15} aria-hidden="true" />;
    case 'rag':
      return <FileSearchIcon size={15} aria-hidden="true" />;
    case 'memory':
      return <DatabaseIcon size={15} aria-hidden="true" />;
    case 'thinking':
      return <BrainIcon size={15} aria-hidden="true" />;
    case 'speaking':
      return <MessageSquareTextIcon size={15} aria-hidden="true" />;
    default:
      return <WrenchIcon size={15} aria-hidden="true" />;
  }
}

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === 'active') {
    return <Loader2Icon className="ai-cot-spin" size={14} aria-hidden="true" />;
  }
  if (status === 'pending') {
    return <ClockIcon size={14} aria-hidden="true" />;
  }
  if (status === 'error') {
    return <AlertCircleIcon size={14} aria-hidden="true" />;
  }
  return <CheckCircle2Icon size={14} aria-hidden="true" />;
}

export function ChainOfThoughtStep({
  kind,
  status,
  label,
  badgeText,
  detail,
}: {
  kind: string;
  status: StepStatus;
  label: string;
  badgeText: string;
  detail?: string;
}) {
  return (
    <div className={`ai-cot-step ai-cot-step-${status}`}>
      <span className="ai-cot-step-icon">
        <KindIcon kind={kind} />
      </span>
      <span className="ai-cot-step-label">{label}</span>
      {detail && <span className="ai-cot-step-detail">{detail}</span>}
      <span className={`ai-cot-badge ai-cot-badge-${status}`}>
        <StatusIcon status={status} />
        <span>{badgeText}</span>
      </span>
    </div>
  );
}
