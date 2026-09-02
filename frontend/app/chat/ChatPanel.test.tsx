import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatRequestError, streamAnswer } from "@/lib/api-client";

import ChatPanel from "./ChatPanel";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    // crypto.randomUUID would do fine, but a fixed token makes the
    // assertions on what was posted readable.
    createSessionToken: () => "b".repeat(32),
    streamAnswer: vi.fn(),
  };
});

const streamAnswerMock = vi.mocked(streamAnswer);

function yielding(...chunks: string[]) {
  return async function* () {
    for (const chunk of chunks) {
      yield chunk;
    }
  };
}

function failing(error: unknown) {
  return async function* (): AsyncGenerator<string> {
    throw error;
  };
}

function submit(question = "czy warto?") {
  fireEvent.change(screen.getByLabelText("Twoje pytanie"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Zapytaj" }));
}

beforeEach(() => {
  streamAnswerMock.mockReset();
});

describe("ChatPanel", () => {
  it("starts in the empty state", () => {
    render(<ChatPanel />);

    expect(screen.getByText("Nie zadano jeszcze pytania")).toBeInTheDocument();
  });

  it("will not send an empty or whitespace-only question", () => {
    render(<ChatPanel />);
    const button = screen.getByRole("button", { name: "Zapytaj" });

    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Twoje pytanie"), { target: { value: "   " } });

    expect(button).toBeDisabled();
  });

  // Acceptance criterion 1: on submit, not on first byte. Asserted without
  // waitFor on purpose - if this needed waiting, the criterion would be
  // unmet however fast the wait resolved.
  it("shows the typing state synchronously when the question is sent", () => {
    // Never resolves: the point is that the indicator is already on screen
    // while the request is still outstanding.
    streamAnswerMock.mockImplementation(async function* () {
      await new Promise(() => {});
      yield "chat.placeholder_answer.chunk_0\n";
    });

    render(<ChatPanel />);
    submit();

    expect(screen.getByText("Asystent pisze")).toBeInTheDocument();
    expect(screen.queryByText("Nie zadano jeszcze pytania")).not.toBeInTheDocument();
  });

  it("disables sending while an answer is on its way", () => {
    streamAnswerMock.mockImplementation(async function* () {
      await new Promise(() => {});
    });

    render(<ChatPanel />);
    submit();

    expect(screen.getByRole("button", { name: "Zapytaj" })).toBeDisabled();
  });

  it("resolves the streamed translation keys into Polish copy", async () => {
    // The backend streams keys, one per line, never prose.
    streamAnswerMock.mockImplementation(
      yielding("chat.placeholder_answer.chunk_0\nchat.placeholder_answer.chunk_1\n"),
    );

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText(/To jest odpowiedź zastępcza/)).toBeInTheDocument();
    });
    expect(screen.getByText(/nie korzysta jeszcze z bazy wiedzy fundacji/)).toBeInTheDocument();
  });

  it("reassembles a key split across two chunks", async () => {
    streamAnswerMock.mockImplementation(
      yielding("chat.placeholder_", "answer.chunk_0\n"),
    );

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText(/To jest odpowiedź zastępcza/)).toBeInTheDocument();
    });
  });

  // A network chunk can end mid-key, which resolves to nothing at all. The
  // typing state has to survive that: an empty answer box in its place loses
  // the loading state while the request is still running.
  it("keeps the typing state while a chunk carries no complete key yet", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    streamAnswerMock.mockImplementation(async function* () {
      yield "chat.placeholder_";
      await gate;
      yield "answer.chunk_0\n";
    });

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(streamAnswerMock).toHaveBeenCalledOnce();
    });
    expect(screen.getByText("Asystent pisze")).toBeInTheDocument();
    expect(screen.queryByText("Odpowiedź asystenta")).not.toBeInTheDocument();

    release();
    await waitFor(() => {
      expect(screen.getByText(/To jest odpowiedź zastępcza/)).toBeInTheDocument();
    });
  });

  // The mirror of `streamAnswer`'s "200 with no body" guard: if nothing in
  // the stream resolves, a blank answer box must not stand in for the answer.
  it("fails instead of showing a blank answer when no key resolves", async () => {
    streamAnswerMock.mockImplementation(yielding("chat.unknown_a\nchat.unknown_b\n"));

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText("Nie udało się połączyć")).toBeInTheDocument();
    });
    expect(screen.queryByText("Odpowiedź asystenta")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeInTheDocument();
  });

  it("drops a key the dictionary does not know instead of showing it", async () => {
    streamAnswerMock.mockImplementation(
      yielding("chat.placeholder_answer.chunk_0\nchat.placeholder_answer.chunk_99\n"),
    );

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText(/To jest odpowiedź zastępcza/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/chunk_99/)).not.toBeInTheDocument();
  });

  it.each([
    ["unreachable", "Nie udało się połączyć"],
    ["database_unavailable", "Asystent jest chwilowo niedostępny"],
    ["invalid_question", "Nie możemy przyjąć tego pytania"],
  ] as const)("shows Polish copy with a retry for the %s failure", async (failure, title) => {
    streamAnswerMock.mockImplementation(failing(new ChatRequestError(failure)));

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText(title)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeInTheDocument();
  });

  it("re-sends the question that was asked, not whatever is in the box now", async () => {
    streamAnswerMock.mockImplementation(failing(new ChatRequestError("unreachable")));

    render(<ChatPanel />);
    submit("pierwsze pytanie");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Spróbuj ponownie" })).toBeInTheDocument();
    });

    // The parent edits the box while the failure is on screen.
    fireEvent.change(screen.getByLabelText("Twoje pytanie"), { target: { value: "coś innego" } });
    fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));

    await waitFor(() => {
      expect(streamAnswerMock).toHaveBeenCalledTimes(2);
    });
    expect(streamAnswerMock.mock.calls[1][0].question).toBe("pierwsze pytanie");
  });

  // T-61: the limit is the funnel's conversion point, so it sends the parent
  // to registration rather than offering a retry that cannot succeed.
  it("sends the parent onward instead of offering a retry when the limit is reached", async () => {
    streamAnswerMock.mockImplementation(failing(new ChatRequestError("limit_reached")));

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText("To już wszystkie pytania na teraz")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Załóż darmowe konto" })).toHaveAttribute(
      "href",
      "/account",
    );
    expect(screen.queryByRole("button", { name: "Spróbuj ponownie" })).not.toBeInTheDocument();
  });

  it("shows none of an unexpected error's detail on screen", async () => {
    // Not a ChatRequestError, so nothing has classified it. It still has to
    // land as ordinary Polish copy: this message is exactly the kind of
    // string T-63 forbids showing a parent.
    streamAnswerMock.mockImplementation(
      failing(new Error("provider Foo rejected: system prompt line 3, token sk-secret")),
    );

    render(<ChatPanel />);
    submit();

    await waitFor(() => {
      expect(screen.getByText("Nie udało się połączyć")).toBeInTheDocument();
    });
    expect(document.body.textContent).not.toContain("Foo");
    expect(document.body.textContent).not.toContain("sk-secret");
    expect(document.body.textContent).not.toContain("system prompt");
  });
});
