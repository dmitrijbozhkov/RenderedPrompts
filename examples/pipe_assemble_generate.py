class Pipe:
    async def pipe(
        self,
        body: dict[str, Any],
        __chat_id__: str,
        __event_emitter__=None,
    ):
        context = PipeContext(
            event_emitter=__event_emitter__
        )

        builder_session = get_builder_session(
            __chat_id__
        )

        user_input = self._latest_user_message(body)

        # ====================================================
        # 1–2. Run the builder until terminal assemble_response
        # ====================================================

        await context.status(
            "Gathering context…"
        )

        builder_run = Runner.run_streamed(
            starting_agent=builder_agent,
            input=user_input,
            context=context,
            session=builder_session,
            max_turns=12,
        )

        async for event in builder_run.stream_events():
            # Builder tools notify OpenWebUI themselves through
            # PipeContext.event_emitter.
            #
            # Usually, nothing should be yielded as assistant content
            # here because the builder is expected to produce tool calls,
            # not user-facing prose.
            #
            # If your builder intentionally emits visible text, you could
            # forward ResponseTextDeltaEvent here.
            pass

        # A streaming run must be drained before final_output and session
        # persistence are considered complete.
        raw_assembly = builder_run.final_output

        if not isinstance(raw_assembly, str):
            raise TypeError(
                "assemble_response must return a JSON string."
            )

        # ====================================================
        # 3. Parse assemble_response data
        # ====================================================

        assembly = AssembleResponseData.model_validate_json(
            raw_assembly
        )

        # ====================================================
        # 4. Run one-turn generator and yield its stream
        # ====================================================

        await context.status(
            "Writing response…"
        )

        generation_run = Runner.run_streamed(
            starting_agent=response_agent,
            input=make_generation_input(
                body,
                assembly,
            ),

            # One model invocation; this agent has no tools.
            max_turns=1,
        )

        async for event in generation_run.stream_events():
            if (
                event.type == "raw_response_event"
                and isinstance(
                    event.data,
                    ResponseTextDeltaEvent,
                )
            ):
                delta = event.data.delta

                if delta:
                    # Plain strings are sufficient for an OpenWebUI Pipe.
                    yield delta

        final_response = generation_run.final_output

        if not isinstance(final_response, str):
            raise TypeError(
                "Response generator did not return text."
            )

        # ====================================================
        # 5. Add final response to builder history
        # ====================================================

        await builder_session.add_items(
            [
                {
                    "role": "assistant",
                    "content": final_response,
                }
            ]
        )

        await context.status(
            "Response complete",
            done=True,
        )

    @staticmethod
    def _latest_user_message(
        body: dict[str, Any],
    ) -> str:
        for message in reversed(
            body.get("messages", [])
        ):
            if (
                message.get("role") == "user"
                and isinstance(
                    message.get("content"),
                    str,
                )
            ):
                return message["content"]

        raise ValueError(
            "No user message was provided."
        )