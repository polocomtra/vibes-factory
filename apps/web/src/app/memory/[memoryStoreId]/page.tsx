"use client";

import { useParams } from "next/navigation";

import { MemoryStoreDetailView } from "../../../components/memory-store-detail";

export default function MemoryStorePage() {
    const params = useParams<{ memoryStoreId: string }>();
    const memoryStoreId = params.memoryStoreId;

    return <MemoryStoreDetailView memoryStoreId={memoryStoreId} />;
}
