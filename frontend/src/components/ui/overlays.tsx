import { AlertDialog as AD, DropdownMenu as DM } from "radix-ui";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirm,
  danger,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirm: string;
  danger?: boolean;
  onConfirm: () => void;
}) {
  return (
    <AD.Root open={open} onOpenChange={onOpenChange}>
      <AD.Portal>
        <AD.Overlay className="animate-fade-in fixed inset-0 z-50 bg-(--overlay) backdrop-blur-[2px]" />
        <AD.Content className="animate-pop-in border-line-strong bg-surface shadow-pop fixed top-1/2 left-1/2 z-50 w-[min(440px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-xl border p-5">
          <AD.Title className="text-[15px] font-semibold tracking-tight">{title}</AD.Title>
          <AD.Description className="text-ink-2 mt-1.5 text-[13.5px] leading-relaxed">
            {description}
          </AD.Description>
          <div className="mt-5 flex justify-end gap-2">
            <AD.Cancel asChild>
              <Button variant="secondary">Cancel</Button>
            </AD.Cancel>
            <AD.Action asChild>
              <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
                {confirm}
              </Button>
            </AD.Action>
          </div>
        </AD.Content>
      </AD.Portal>
    </AD.Root>
  );
}

export const Menu = DM.Root;
export const MenuTrigger = DM.Trigger;

export function MenuContent({ children, align = "end" }: { children: ReactNode; align?: "start" | "end" }) {
  return (
    <DM.Portal>
      <DM.Content
        align={align}
        sideOffset={6}
        className="animate-pop-in border-line-strong bg-surface shadow-pop z-50 min-w-48 rounded-lg border p-1"
      >
        {children}
      </DM.Content>
    </DM.Portal>
  );
}

export function MenuItem({
  children,
  onSelect,
  icon,
  danger,
  checked,
}: {
  children: ReactNode;
  onSelect?: () => void;
  icon?: ReactNode;
  danger?: boolean;
  checked?: boolean;
}) {
  return (
    <DM.Item
      onSelect={onSelect}
      className={cn(
        "text-ink data-highlighted:bg-surface-2 [&_svg]:text-muted flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-[13px] outline-none select-none [&_svg]:size-4",
        danger && "text-critical-ink [&_svg]:text-critical-ink",
      )}
    >
      {icon}
      <span className="flex-1">{children}</span>
      {checked && <span className="bg-ink size-1.5 rounded-full" />}
    </DM.Item>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <DM.Label className="text-muted px-2 pt-1.5 pb-1 text-[11px] font-medium">{children}</DM.Label>;
}

export function MenuSeparator() {
  return <DM.Separator className="bg-line my-1 h-px" />;
}
