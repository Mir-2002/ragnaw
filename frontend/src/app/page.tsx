import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-6 px-4 py-16 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">RAGNaw</h1>
        <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">
          Ask anything about Pokémon. Answers are grounded in PokeAPI data.
        </p>
        <BackendStatus />
      </main>
      <footer className="px-4 py-6 text-center text-xs text-zinc-500">
        Unofficial fan project. Pokémon © Nintendo, Game Freak, Creatures. Data from{" "}
        <a href="https://pokeapi.co" className="underline underline-offset-2">
          PokeAPI
        </a>
        .
      </footer>
    </div>
  );
}
