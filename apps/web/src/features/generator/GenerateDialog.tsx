"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ApiError } from "@/lib/api/client";
import type { Collection } from "@/features/intake/api";
import { createGeneration, generationKeys } from "./api";
import {
  PRESETS,
  PROFILES,
  PROFILE_DESCRIPTIONS,
  randomSeed,
  validateGenerate,
  type GenerateErrors,
  type Preset,
  type Profile,
} from "./params";

const inputClass =
  "w-full rounded-sm border border-rule-strong bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint disabled:opacity-60";

export interface GenerateDialogProps {
  matterId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Earlier generated collections of this matter (re-delivery bases). */
  baseOptions: Collection[];
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-[12px] text-accent">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function GenerateDialog({ matterId, open, onOpenChange, baseOptions }: GenerateDialogProps) {
  const queryClient = useQueryClient();
  const [seed, setSeed] = useState(() => String(randomSeed()));
  const [preset, setPreset] = useState<Preset>("small");
  const [profile, setProfile] = useState<Profile>("default");
  const [messages, setMessages] = useState("");
  const [conversations, setConversations] = useState("");
  const [baseId, setBaseId] = useState("");
  const [errors, setErrors] = useState<GenerateErrors & { form?: string }>({});

  const base = baseOptions.find((c) => c.id === baseId);
  const locked = base?.generation ?? null;
  const effectivePreset = (locked?.preset as Preset | undefined) ?? preset;
  const effectiveProfile = (locked?.profile as Profile | undefined) ?? profile;

  const mutation = useMutation({
    mutationFn: (body: Parameters<typeof createGeneration>[1]) => createGeneration(matterId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: generationKeys.list(matterId) });
      setSeed(String(randomSeed()));
      setBaseId("");
      setErrors({});
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      if (error instanceof ApiError) {
        const field = error.details?.field;
        if (error.code === "GENERATION_PARAMS_INVALID" && typeof field === "string") {
          setErrors({ [field]: error.message });
          return;
        }
        setErrors({ form: error.message });
        return;
      }
      setErrors({ form: "Could not reach the API. Try again." });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = locked
      ? validateGenerate({ seed, preset: "small", messages: "", conversations: "" })
      : validateGenerate({ seed, preset, messages, conversations });
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    mutation.mutate({
      seed: Number(seed),
      preset: effectivePreset,
      profile: effectiveProfile,
      messages: !locked && preset === "custom" ? Number(messages) : null,
      conversations: !locked && preset === "custom" ? Number(conversations) : null,
      overlap_of_collection_id: base ? base.id : null,
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setErrors({});
        onOpenChange(next);
      }}
      title="Generate synthetic export"
      description="Create a reproducible Slack export with known defects for this matter."
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field id="gen-seed" label="Seed" error={errors.seed}>
          <input
            id="gen-seed"
            inputMode="numeric"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            aria-invalid={errors.seed ? true : undefined}
            aria-describedby={errors.seed ? "gen-seed-error" : undefined}
            className={inputClass}
          />
        </Field>
        <Field id="gen-preset" label="Preset">
          <select
            id="gen-preset"
            value={effectivePreset}
            disabled={Boolean(locked)}
            onChange={(e) => setPreset(e.target.value as Preset)}
            className={inputClass}
          >
            {PRESETS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Field>
        {effectivePreset === "custom" && !locked ? (
          <>
            <Field id="gen-messages" label="Messages (1,000–1,000,000)" error={errors.messages}>
              <input
                id="gen-messages"
                inputMode="numeric"
                value={messages}
                onChange={(e) => setMessages(e.target.value)}
                aria-invalid={errors.messages ? true : undefined}
                aria-describedby={errors.messages ? "gen-messages-error" : undefined}
                className={inputClass}
              />
            </Field>
            <Field id="gen-conversations" label="Conversations (1–5,000)" error={errors.conversations}>
              <input
                id="gen-conversations"
                inputMode="numeric"
                value={conversations}
                onChange={(e) => setConversations(e.target.value)}
                aria-invalid={errors.conversations ? true : undefined}
                aria-describedby={errors.conversations ? "gen-conversations-error" : undefined}
                className={inputClass}
              />
            </Field>
          </>
        ) : null}
        <Field id="gen-profile" label="Anomaly profile">
          <select
            id="gen-profile"
            value={effectiveProfile}
            disabled={Boolean(locked)}
            onChange={(e) => setProfile(e.target.value as Profile)}
            className={inputClass}
          >
            {PROFILES.map((p) => (
              <option key={p} value={p}>
                {`${p} — ${PROFILE_DESCRIPTIONS[p]}`}
              </option>
            ))}
          </select>
        </Field>
        <Field id="gen-base" label="Generate as re-delivery of">
          <select
            id="gen-base"
            value={baseId}
            disabled={baseOptions.length === 0}
            onChange={(e) => setBaseId(e.target.value)}
            className={inputClass}
          >
            <option value="">None</option>
            {baseOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {`${c.original_filename} (seed ${c.generation?.seed})`}
              </option>
            ))}
          </select>
        </Field>
        {errors.form ? (
          <p role="alert" className="text-[13px] text-accent">
            {errors.form}
          </p>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-rule pt-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={mutation.isPending}>
            Generate
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
