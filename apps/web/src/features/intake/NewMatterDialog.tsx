"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ApiError } from "@/lib/api/client";
import { createMatter, matterKeys } from "./api";

export const NAME_ERROR = "Name must be 3–80 characters";
const DESCRIPTION_ERROR = "Description must be at most 500 characters";

interface FieldErrors {
  name?: string;
  description?: string;
  form?: string;
}

const inputClass =
  "w-full rounded-sm border border-rule-strong bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint";

export interface NewMatterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NewMatterDialog({ open, onOpenChange }: NewMatterDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});

  const mutation = useMutation({
    mutationFn: createMatter,
    onSuccess: async (matter) => {
      await queryClient.invalidateQueries({ queryKey: matterKeys.all });
      reset();
      onOpenChange(false);
      router.push(`/matters/${matter.id}/collections`);
    },
    onError: (error: unknown) => {
      if (error instanceof ApiError) {
        if (error.code === "MATTER_NAME_INVALID" || error.code === "MATTER_NAME_TAKEN") {
          setErrors({ name: error.message });
          return;
        }
        if (error.code === "MATTER_DESCRIPTION_INVALID") {
          setErrors({ description: error.message });
          return;
        }
        setErrors({ form: error.message });
        return;
      }
      setErrors({ form: "Could not reach the API. Try again." });
    },
  });

  function reset() {
    setName("");
    setDescription("");
    setErrors({});
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedDescription = description.trim();
    const next: FieldErrors = {};
    if (trimmedName.length < 3 || trimmedName.length > 80) next.name = NAME_ERROR;
    if (trimmedDescription.length > 500) next.description = DESCRIPTION_ERROR;
    setErrors(next);
    if (next.name || next.description) return;
    mutation.mutate({ name: trimmedName, description: trimmedDescription || null });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
      title="New matter"
      description="A matter groups the Slack export collections and runs for one case."
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="matter-name" className="text-[13px] font-medium">
            Name
          </label>
          <input
            id="matter-name"
            name="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? "matter-name-error" : undefined}
            autoComplete="off"
            className={inputClass}
          />
          {errors.name ? (
            <p id="matter-name-error" role="alert" className="text-[12px] text-accent">
              {errors.name}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="matter-description" className="text-[13px] font-medium">
            Description <span className="font-normal text-ink-faint">(optional)</span>
          </label>
          <textarea
            id="matter-description"
            name="description"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={errors.description ? "matter-description-error" : undefined}
            className={inputClass}
          />
          {errors.description ? (
            <p id="matter-description-error" role="alert" className="text-[12px] text-accent">
              {errors.description}
            </p>
          ) : null}
        </div>
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
            Create matter
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
