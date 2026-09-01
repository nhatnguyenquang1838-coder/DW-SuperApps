import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import LoginPage from "@/app/login/page";

describe("LoginPage (/login)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders DW Run Observatory login screen", () => {
    render(<LoginPage />);
    expect(screen.getByText("DW Run Observatory")).toBeTruthy();
    expect(screen.getByText("Sign in to your account")).toBeTruthy();
  });

  it("email and password controls present and correctly labelled", () => {
    render(<LoginPage />);
    const email = screen.getByLabelText(/email/i);
    const password = screen.getByLabelText(/password/i);
    expect(email).toBeTruthy();
    expect(password).toBeTruthy();
    expect(email.getAttribute("type")).toBe("email");
    expect(password.getAttribute("type")).toBe("password");
  });

  it("empty submit produces deterministic validation feedback", () => {
    render(<LoginPage />);
    fireEvent.submit(screen.getByTestId("login-form"));
    expect(screen.getByText("Email is required")).toBeTruthy();
    expect(screen.getByText("Password is required")).toBeTruthy();
  });

  it("valid local submit produces deterministic loading/feedback state", () => {
    vi.useFakeTimers();
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.submit(screen.getByTestId("login-form"));
    expect(screen.getAllByText("Signing in...").length).toBeGreaterThanOrEqual(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("Sign-in completed (local only)")).toBeTruthy();
  });

  it("does not call external authentication", () => {
    vi.useFakeTimers();
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(new Response());
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.submit(screen.getByTestId("login-form"));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
