import React from "react";
import MDIcon from "@react-native-vector-icons/material-design-icons";
import type { ComponentProps } from "react";

// Single icon wrapper so screens never import the vendor package directly.
type MDIProps = ComponentProps<typeof MDIcon>;
export type IconName = MDIProps["name"];

export function Icon(props: { name: IconName; size?: number; color?: string }) {
  return <MDIcon name={props.name} size={props.size ?? 22} color={props.color} />;
}
