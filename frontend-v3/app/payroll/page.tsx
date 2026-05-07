"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Banknote, FileText, Plus, ReceiptText, Search, Send, Trash2, WalletCards } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePayrollEmployees, usePayrollRuns } from "@/hooks/useData";
import { api, PayrollEmployee, PayrollRun } from "@/lib/api";

const inputClass =
  "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

function ore(value: string) {
  const normalized = value.replace(/\s/g, "").replace(",", ".");
  return Math.round((parseFloat(normalized) || 0) * 100);
}

function sek(value: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK" }).format((value || 0) / 100);
}

function payrollPaymentDate(yearText: string, monthText: string, dayText: string) {
  const year = parseInt(yearText);
  const month = parseInt(monthText);
  const day = parseInt(dayText) || 25;
  const lastDay = new Date(year, month, 0).getDate();
  return `${year}-${String(month).padStart(2, "0")}-${String(Math.min(day, lastDay)).padStart(2, "0")}`;
}

export default function PayrollPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [employeeName, setEmployeeName] = useState("");
  const [personalNumber, setPersonalNumber] = useState("");
  const [email, setEmail] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [salaryEmployeeId, setSalaryEmployeeId] = useState("");
  const [grossSalary, setGrossSalary] = useState("");
  const [preliminaryTax, setPreliminaryTax] = useState("");
  const [employerFeePercent, setEmployerFeePercent] = useState("31.42");
  const [paymentDay, setPaymentDay] = useState("25");
  const [runYear, setRunYear] = useState(String(new Date().getFullYear()));
  const [runMonth, setRunMonth] = useState(String(new Date().getMonth() + 1));
  const [runPaymentDay, setRunPaymentDay] = useState("25");
  const [bankTransactionIds, setBankTransactionIds] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const employeesQuery = usePayrollEmployees(search || undefined);
  const runsQuery = usePayrollRuns();
  const employees: PayrollEmployee[] = employeesQuery.data?.employees || [];
  const runs: PayrollRun[] = runsQuery.data?.payroll_runs || [];

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["payroll-employees"] }),
      queryClient.invalidateQueries({ queryKey: ["payroll-runs"] }),
    ]);
  };

  const message = (err: any, fallback: string) => {
    const detail = err?.response?.data?.detail;
    const msg = detail?.error || detail || err?.message || fallback;
    return typeof msg === "string" ? msg : JSON.stringify(msg);
  };

  const createEmployee = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const employee = await api.createPayrollEmployee({
        name: employeeName.trim(),
        personal_number: personalNumber.trim() || undefined,
        email: email.trim() || undefined,
        bank_account: bankAccount.trim() || undefined,
      });
      setEmployeeName("");
      setPersonalNumber("");
      setEmail("");
      setBankAccount("");
      setSalaryEmployeeId(employee.id);
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte skapa anställd."));
    } finally {
      setSubmitting(false);
    }
  };

  const saveSalary = async (event: FormEvent) => {
    event.preventDefault();
    if (!salaryEmployeeId) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.setPayrollSalary(salaryEmployeeId, {
        gross_monthly_salary: ore(grossSalary),
        preliminary_tax: ore(preliminaryTax),
        employer_fee_rate_bp: Math.round((parseFloat(employerFeePercent.replace(",", ".")) || 0) * 100),
        employer_fee_amount: null,
        payment_day: parseInt(paymentDay) || 25,
        active: true,
      });
      setGrossSalary("");
      setPreliminaryTax("");
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte spara löneinställningen."));
    } finally {
      setSubmitting(false);
    }
  };

  const createRun = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const createdRun = await api.createPayrollRun({
        year: parseInt(runYear),
        month: parseInt(runMonth),
        payment_date: payrollPaymentDate(runYear, runMonth, runPaymentDay),
      });
      await api.generatePayrollRun(createdRun.id);
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte skapa lönekörning."));
    } finally {
      setSubmitting(false);
    }
  };

  const deleteRun = async (runId: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await api.deletePayrollRun(runId);
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte ta bort lönekörningen."));
    } finally {
      setSubmitting(false);
    }
  };

  const generateRun = async (runId: string) => {
    setSubmitting(true);
    setError(null);
    try {
      await api.generatePayrollRun(runId);
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte generera lönespecifikationer."));
    } finally {
      setSubmitting(false);
    }
  };

  const markSent = async (payslipId: string) => {
    await api.markPayslipSent(payslipId);
    await invalidate();
  };

  const bookPayslip = async (payslipId: string) => {
    const txId = bankTransactionIds[payslipId]?.trim();
    if (!txId) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.bookPayslip(payslipId, txId);
      await invalidate();
    } catch (err: any) {
      setError(message(err, "Kunde inte bokföra lönespecifikationen."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1280px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight lg:text-3xl">
            <WalletCards className="h-6 w-6 text-primary" />
            Lön
          </h1>
          <p className="mt-1 text-muted-foreground">Register, lönespecifikationer och bokföringsunderlag för nettolöneutbetalningar.</p>
        </div>
      </div>

      {error && <p className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <form onSubmit={createEmployee} className="space-y-4">
              <div className="flex items-center gap-2">
                <Plus className="h-4 w-4 text-primary" />
                <h2 className="font-semibold">Ny anställd</h2>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-sm font-medium">
                  Namn
                  <input className={`${inputClass} mt-1`} value={employeeName} onChange={(e) => setEmployeeName(e.target.value)} required />
                </label>
                <label className="text-sm font-medium">
                  Personnummer
                  <input className={`${inputClass} mt-1`} value={personalNumber} onChange={(e) => setPersonalNumber(e.target.value)} />
                </label>
                <label className="text-sm font-medium">
                  E-post
                  <input className={`${inputClass} mt-1`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
                <label className="text-sm font-medium">
                  Bankkonto
                  <input className={`${inputClass} mt-1`} value={bankAccount} onChange={(e) => setBankAccount(e.target.value)} />
                </label>
              </div>
              <Button type="submit" disabled={submitting}>{submitting ? "Sparar..." : "Skapa anställd"}</Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <form onSubmit={saveSalary} className="space-y-4">
              <div className="flex items-center gap-2">
                <Banknote className="h-4 w-4 text-primary" />
                <h2 className="font-semibold">Löneinställning</h2>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-sm font-medium md:col-span-2">
                  Anställd
                  <select className={`${inputClass} mt-1`} value={salaryEmployeeId} onChange={(e) => setSalaryEmployeeId(e.target.value)} required>
                    <option value="">Välj anställd</option>
                    {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name}</option>)}
                  </select>
                </label>
                <label className="text-sm font-medium">
                  Bruttomånadslön
                  <input className={`${inputClass} mt-1`} inputMode="decimal" value={grossSalary} onChange={(e) => setGrossSalary(e.target.value)} required />
                </label>
                <label className="text-sm font-medium">
                  Preliminärskatt
                  <input className={`${inputClass} mt-1`} inputMode="decimal" value={preliminaryTax} onChange={(e) => setPreliminaryTax(e.target.value)} required />
                </label>
                <label className="text-sm font-medium">
                  Arbetsgivaravgift %
                  <input className={`${inputClass} mt-1`} inputMode="decimal" value={employerFeePercent} onChange={(e) => setEmployerFeePercent(e.target.value)} />
                </label>
                <label className="text-sm font-medium">
                  Utbetalningsdag
                  <input className={`${inputClass} mt-1`} inputMode="numeric" value={paymentDay} onChange={(e) => setPaymentDay(e.target.value)} />
                </label>
              </div>
              <Button type="submit" disabled={submitting || !salaryEmployeeId}>Spara lön</Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input className={`${inputClass} pl-9`} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Sök anställd..." />
            </div>
          </div>
          {employeesQuery.isLoading ? (
            <div className="space-y-3 p-6">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : employees.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">Inga anställda hittades.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="p-4 text-left font-medium text-muted-foreground">Anställd</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">E-post</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Brutto</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Skatt</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Arbetsgivaravgift</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map((employee) => (
                    <tr key={employee.id} className="border-b last:border-0">
                      <td className="p-4 font-medium">{employee.name}</td>
                      <td className="p-4">{employee.email || "-"}</td>
                      <td className="p-4 text-right">{employee.salary_setting ? sek(employee.salary_setting.gross_monthly_salary) : "-"}</td>
                      <td className="p-4 text-right">{employee.salary_setting ? sek(employee.salary_setting.preliminary_tax) : "-"}</td>
                      <td className="p-4 text-right">{employee.salary_setting ? sek(employee.salary_setting.calculated_employer_fee) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-5 p-5">
          <div>
            <h2 className="flex items-center gap-2 font-semibold">
              <ReceiptText className="h-4 w-4 text-primary" />
              Månadens lönekörning
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Skapa en lönekörning per månad. Knappen skapar direkt lönespecifikationer för alla aktiva anställda med löneinställning.
            </p>
          </div>
          <form onSubmit={createRun} className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
            <label className="text-sm font-medium">
              År
              <input className={`${inputClass} mt-1`} inputMode="numeric" value={runYear} onChange={(e) => setRunYear(e.target.value)} />
            </label>
            <label className="text-sm font-medium">
              Månad
              <input className={`${inputClass} mt-1`} inputMode="numeric" value={runMonth} onChange={(e) => setRunMonth(e.target.value)} />
            </label>
            <label className="text-sm font-medium">
              Utbetalningsdag
              <input className={`${inputClass} mt-1`} inputMode="numeric" min={1} max={31} value={runPaymentDay} onChange={(e) => setRunPaymentDay(e.target.value)} />
            </label>
            <Button type="submit" disabled={submitting}>
              <ReceiptText className="mr-2 h-4 w-4" />
              Skapa månadens lönespecar
            </Button>
          </form>

          {runsQuery.isLoading ? (
            <div className="space-y-3">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
          ) : runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Inga lönekörningar finns ännu.</p>
          ) : (
            <div className="space-y-5">
              {runs.map((run) => (
                <section key={run.id} className="rounded-lg border">
                  <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="font-semibold">Lönekörning {run.year}-{String(run.month).padStart(2, "0")}</h2>
                      <p className="text-sm text-muted-foreground">Utbetalning {run.payment_date} · {run.status}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {run.status === "draft" && <Button onClick={() => generateRun(run.id)} disabled={submitting || run.validation?.valid === false}>Skapa lönespecifikationer för månaden</Button>}
                      {run.status !== "booked" && (
                        <Button variant="outline" onClick={() => deleteRun(run.id)} disabled={submitting}>
                          <Trash2 className="mr-2 h-4 w-4" />
                          Ta bort
                        </Button>
                      )}
                    </div>
                  </div>
                  {run.validation && (run.validation.errors.length > 0 || run.validation.warnings.length > 0) && (
                    <div className="space-y-2 border-b p-4">
                      {run.validation.errors.map((item) => (
                        <p key={item.code} className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
                          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                          {item.message}
                        </p>
                      ))}
                      {run.validation.warnings.map((item) => (
                        <p key={item.code} className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
                          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                          {item.message}
                        </p>
                      ))}
                    </div>
                  )}
                  <div className="grid gap-3 border-b p-4 text-sm md:grid-cols-5">
                    <div><span className="text-muted-foreground">Brutto</span><br />{sek(run.total_gross_salary)}</div>
                    <div><span className="text-muted-foreground">Skatt</span><br />{sek(run.total_preliminary_tax)}</div>
                    <div><span className="text-muted-foreground">Netto</span><br />{sek(run.total_net_salary)}</div>
                    <div><span className="text-muted-foreground">Avgifter</span><br />{sek(run.total_employer_fee)}</div>
                    <div><span className="text-muted-foreground">Total kostnad</span><br />{sek(run.total_employer_cost)}</div>
                  </div>
                  {run.payslips.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b bg-muted/50">
                            <th className="p-4 text-left font-medium text-muted-foreground">Anställd</th>
                            <th className="p-4 text-right font-medium text-muted-foreground">Netto</th>
                            <th className="p-4 text-left font-medium text-muted-foreground">Status</th>
                            <th className="p-4 text-left font-medium text-muted-foreground">Banktransaktion</th>
                            <th className="p-4 text-right font-medium text-muted-foreground">Åtgärder</th>
                          </tr>
                        </thead>
                        <tbody>
                          {run.payslips.map((payslip) => (
                            <tr key={payslip.id} className="border-b last:border-0">
                              <td className="p-4 font-medium">{payslip.employee_name}</td>
                              <td className="p-4 text-right">{sek(payslip.net_salary)}</td>
                              <td className="p-4">{payslip.status}</td>
                              <td className="p-4">
                                <input
                                  className={inputClass}
                                  value={bankTransactionIds[payslip.id] || ""}
                                  onChange={(e) => setBankTransactionIds((prev) => ({ ...prev, [payslip.id]: e.target.value }))}
                                  placeholder="bank_transaction_id"
                                  disabled={!!payslip.voucher_id}
                                />
                              </td>
                              <td className="p-4">
                                <div className="flex justify-end gap-2">
                                  <Link href={api.getPayslipPdfUrl(payslip.id)} target="_blank">
                                    <Button variant="outline" size="sm">
                                      <FileText className="h-4 w-4" />
                                    </Button>
                                  </Link>
                                  <Button variant="outline" size="sm" onClick={() => markSent(payslip.id)} disabled={payslip.status !== "generated"}>
                                    <Send className="h-4 w-4" />
                                  </Button>
                                  <Button size="sm" onClick={() => bookPayslip(payslip.id)} disabled={!!payslip.voucher_id || !bankTransactionIds[payslip.id]}>
                                    Bokför
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
