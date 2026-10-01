"use client";

import { useParams } from "next/navigation";

import { AppShell } from "../../../components/app-shell";
import { MemoryStoreDetailView } from "../../../components/memory-store-detail";

export default function MemoryStorePage() {
    const params = useParams<{ memoryStoreId: string }>();
    const memoryStoreId = params.memoryStoreId;

    return <AppShell><MemoryStoreDetailView memoryStoreId={memoryStoreId} /></AppShell>;
}
