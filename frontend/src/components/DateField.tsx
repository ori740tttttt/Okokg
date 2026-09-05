import React, { useState } from "react";
import { Modal, Pressable, Text } from "react-native";
import { Calendar } from "react-native-calendars";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { Icon } from "./Icon";

// Reusable date picker field that opens a calendar modal. Value is YYYY-MM-DD.
export function DateField({
  value,
  onChange,
  placeholder,
  minDate,
  testID,
}: {
  value: string;
  onChange: (d: string) => void;
  placeholder?: string;
  minDate?: string;
  testID?: string;
}) {
  const s = useStyles();
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Pressable testID={testID} style={s.wrap} onPress={() => setOpen(true)}>
        <Icon name="calendar-blank-outline" size={18} color={colors.muted} />
        <Text style={[s.txt, !value && { color: colors.muted }]}>{value || placeholder || "Seleziona data"}</Text>
        <Icon name="chevron-down" size={18} color={colors.muted} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={s.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={s.sheet} onPress={(e) => e.stopPropagation()}>
            <Calendar
              testID={`${testID}-calendar`}
              current={value || undefined}
              minDate={minDate}
              markedDates={value ? { [value]: { selected: true, selectedColor: colors.brandPrimary } } : {}}
              onDayPress={(d: { dateString: string }) => {
                onChange(d.dateString);
                setOpen(false);
              }}
              theme={{
                calendarBackground: colors.surfaceSecondary,
                monthTextColor: colors.onSurface,
                textMonthFontFamily: fonts.heading,
                dayTextColor: colors.onSurface,
                arrowColor: colors.brandPrimary,
                todayTextColor: colors.brandPrimary,
                textDayFontFamily: fonts.body,
              }}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: c.surfaceTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 52,
    borderWidth: 1,
    borderColor: c.border,
  },
  txt: { flex: 1, color: c.onSurface, fontSize: 16, fontFamily: fonts.body },
  backdrop: { flex: 1, backgroundColor: "rgba(44,42,40,0.45)", justifyContent: "center", padding: spacing.lg },
  sheet: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, padding: spacing.sm },
}));
