"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useAccountingCorrections,
  useAgentInstructions,
  useAgentInstructionVersions,
} from "@/hooks/useData";
import { api } from "@/lib/api";
import { Brain, FileText, History, Target } from "lucide-react";

export default function LearningPage() {
  const queryClient = useQueryClient();
  const { data: instructionsData } = useAgentInstructions();
  const { data: instructionVersionsData } = useAgentInstructionVersions();
  const { data: correctionsData } = useAccountingCorrections(25);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [instructionDraft, setInstructionDraft] = useState("");
  const [instructionSummary, setInstructionSummary] = useState("");

  const instructionVersions = instructionVersionsData?.versions || [];
  const corrections = correctionsData?.corrections || [];

  useEffect(() => {
    if (instructionsData?.content_markdown) {
      setInstructionDraft(instructionsData.content_markdown);
    }
  }, [instructionsData?.content_markdown]);

  const saveInstructions = async () => {
    setWorking(true);
    setMessage(null);
    try {
      const result = await api.updateAgentInstructions({
        content_markdown: instructionDraft,
        change_summary: instructionSummary || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["agent-instructions"] });
      await queryClient.invalidateQueries({ queryKey: ["agent-instruction-versions"] });
      setInstructionSummary("");
      setMessage(`Instruktioner sparade som version ${result.version}.`);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || "Kunde inte spara instruktionerna.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">Agentinstruktioner</h1>
        <p className="text-muted-foreground mt-1">
          Agentinstruktioner och korrigeringshistorik för direktbokföring
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          title="Aktiv version"
          value={instructionsData?.version || 0}
          icon={FileText}
          color="blue"
        />
        <StatCard
          title="Sparade versioner"
          value={instructionVersions.length}
          icon={History}
          color="violet"
        />
        <StatCard
          title="Korrigeringar"
          value={correctionsData?.total || 0}
          icon={Target}
          color="amber"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            Agentinstruktioner
          </CardTitle>
          <CardDescription>
            Markdown-instruktioner som agenten läser innan den skapar och postar verifikationer direkt.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <textarea
            value={instructionDraft}
            onChange={(event) => setInstructionDraft(event.target.value)}
            className="min-h-[420px] w-full rounded-lg border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="flex flex-col gap-2 md:flex-row">
            <input
              value={instructionSummary}
              onChange={(event) => setInstructionSummary(event.target.value)}
              placeholder="Sammanfattning av ändringen"
              className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <Button onClick={saveInstructions} disabled={working || !instructionDraft.trim()}>
              {working ? "Sparar..." : "Spara ny version"}
            </Button>
          </div>
          {message && <p className="text-sm text-muted-foreground">{message}</p>}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Senaste korrigeringar</CardTitle>
            <CardDescription>
              Spårbara rättelser som agenten kan läsa och använda när instruktionerna förbättras.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {corrections.length > 0 ? (
              <div className="space-y-3">
                {corrections.map((correction: any) => (
                  <div key={correction.id} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-mono">
                        {correction.original_voucher?.series}{correction.original_voucher?.number}
                      </span>
                      <span className="text-muted-foreground">korrigerad med</span>
                      <span className="font-mono">
                        {correction.correction_voucher?.series}{correction.correction_voucher?.number}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {correction.correction_reason || "Ingen anledning angiven."}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState text="Inga korrigeringar finns ännu." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Versionshistorik</CardTitle>
            <CardDescription>
              Tidigare versioner av agentens bokföringsinstruktioner.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {instructionVersions.length > 0 ? (
              <div className="space-y-3">
                {instructionVersions.map((version: any) => (
                  <div key={version.version_id} className="rounded-lg border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <span className="font-medium">Version {version.version}</span>
                      <span className="text-xs text-muted-foreground">{version.created_at}</span>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {version.change_summary || "Ingen sammanfattning."}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState text="Inga versioner finns ännu." />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="py-12 text-center text-muted-foreground">
      <Brain className="h-12 w-12 mx-auto mb-4 opacity-30" />
      <p>{text}</p>
    </div>
  );
}

function StatCard({ title, value, icon: Icon, color }: { title: string; value: number; icon: any; color: string }) {
  const colorMap: Record<string, string> = {
    violet: "bg-violet-100 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400",
    amber: "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400",
    blue: "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${colorMap[color]} mb-3`}>
          <Icon className="h-5 w-5" />
        </div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-sm text-muted-foreground">{title}</p>
      </CardContent>
    </Card>
  );
}
