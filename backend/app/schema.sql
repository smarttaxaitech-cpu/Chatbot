create table if not exists conversations (
  id uuid primary key,
  created_at timestamptz default now()
);

create table if not exists messages (
  id uuid primary key,
  conversation_id uuid references conversations(id) on delete cascade,
  role text not null,
  text text not null,
  created_at timestamptz default now(),

  deductibility_type text,
  category_tag text,
  spending_timing text,
  followup_question text,
  confidence_score double precision,
  raw_llm_json jsonb
);

create table if not exists feedback (
  id uuid primary key,
  conversation_id uuid references conversations(id) on delete cascade,
  message_id uuid references messages(id) on delete cascade,
  rating text not null,
  comment text,
  created_at timestamptz default now()
);