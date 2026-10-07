import 'package:flutter/material.dart';

import '../models/event_view_data.dart';
import '../widgets/event_list_item.dart';

enum EventFilter { all, target, other }

class EventsView extends StatelessWidget {
  const EventsView({
    super.key,
    required this.events,
    required this.filter,
    required this.playingEventId,
    required this.onFilterChanged,
    required this.onOpen,
    required this.onPlay,
  });

  final List<EventViewData> events;
  final EventFilter filter;
  final String? playingEventId;
  final ValueChanged<EventFilter> onFilterChanged;
  final ValueChanged<EventViewData> onOpen;
  final ValueChanged<EventViewData> onPlay;

  List<EventViewData> get _visibleEvents {
    return switch (filter) {
      EventFilter.all => events,
      EventFilter.target => events.where((event) => event.isTarget).toList(),
      EventFilter.other => events.where((event) => !event.isTarget).toList(),
    };
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visibleEvents;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 6, 12, 7),
          child: SegmentedButton<EventFilter>(
            showSelectedIcon: false,
            style: ButtonStyle(
              visualDensity: VisualDensity.compact,
              minimumSize: WidgetStatePropertyAll(Size.fromHeight(38)),
              padding: WidgetStatePropertyAll(
                EdgeInsets.symmetric(horizontal: 10),
              ),
            ),
            segments: const [
              ButtonSegment(value: EventFilter.all, label: Text('全部')),
              ButtonSegment(value: EventFilter.target, label: Text('目標')),
              ButtonSegment(value: EventFilter.other, label: Text('其他')),
            ],
            selected: {filter},
            onSelectionChanged: (selection) {
              onFilterChanged(selection.first);
            },
          ),
        ),
        Expanded(
          child: visible.isEmpty
              ? const _EventsEmptyState()
              : Scrollbar(
                  child: ListView.builder(
                    key: const PageStorageKey('events-scroll'),
                    padding: const EdgeInsets.fromLTRB(12, 2, 12, 18),
                    itemCount: visible.length,
                    itemBuilder: (context, index) {
                      final event = visible[index];
                      return EventListItem(
                        event: event,
                        isPlaying: playingEventId == event.eventId,
                        onTap: () => onOpen(event),
                        onPlay: () => onPlay(event),
                      );
                    },
                  ),
                ),
        ),
      ],
    );
  }
}

class _EventsEmptyState extends StatelessWidget {
  const _EventsEmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.inbox_outlined,
              size: 52,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 14),
            Text(
              '尚無事件',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 6),
            Text(
              '本機偵測事件會顯示在這裡。',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
